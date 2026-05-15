import logging
import time
import re
import pytz
from datetime import timedelta
from django.utils import timezone
from geopy.distance import geodesic
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder
from travel.models import TrackingPoint, TrackingSuggestion, Trip, GlobalSetting, Day

logger = logging.getLogger(__name__)

class TrackingProcessor:
    
    @classmethod
    def get_setting(cls, user, key, default):
        s = GlobalSetting.objects.filter(user=user, key=key).first()
        if s and s.value.strip():
            return s.value.strip()
        return default

    @classmethod
    def _get_maps_link(cls, lat, lon):
        return f"https://www.google.com/maps/search/?api=1&query={float(lat):.6f},{float(lon):.6f}"

    @classmethod
    def reverse_geocode(cls, lat, lon):
        from geopy.geocoders import Photon, Nominatim
        name_parts = []
        category = 'OTHER'
        
        # 1. Try Nominatim for reliable administrative address and category
        try:
            nom = Nominatim(user_agent="urlaubsplanung_app_v4")
            loc_nom = nom.reverse((lat, lon), timeout=5, language='de,en', zoom=18)
            if loc_nom:
                addr = loc_nom.raw.get('address', {})
                # Categories mapping
                cat_map = {
                    'restaurant': 'RESTAURANT', 'cafe': 'RESTAURANT', 'bakery': 'RESTAURANT', 'pub': 'RESTAURANT', 'bar': 'RESTAURANT',
                    'hotel': 'HOTEL', 'guest_house': 'HOTEL', 'apartment': 'HOTEL', 'hostel': 'HOTEL', 'camping_site': 'CAMPING',
                    'beach': 'ACTIVITY', 'peak': 'ACTIVITY', 'historic': 'ACTIVITY', 'tourism': 'ACTIVITY', 'cave_entrance': 'ACTIVITY',
                    'museum': 'ACTIVITY', 'attraction': 'ACTIVITY', 'monument': 'ACTIVITY'
                }
                
                # Get specific POI if available
                poi_keys = ['beach', 'tourism', 'amenity', 'leisure', 'historic', 'shop', 'restaurant', 'natural', 'peak', 'cave_entrance']
                for key in poi_keys:
                    if key in addr:
                        name_parts.append(addr[key])
                        if key in cat_map: category = cat_map[key]
                        elif addr.get(key) in cat_map: category = cat_map[addr.get(key)]
                        break
                
                # Add road and city/village
                road = addr.get('road')
                city = addr.get('city') or addr.get('town') or addr.get('village')
                if road and road not in name_parts: name_parts.append(road)
                if city and city not in name_parts: name_parts.append(city)
        except: pass

        # 2. Try Photon (Komoot) for better "Outdoor" POIs
        try:
            phot = Photon(user_agent="urlaubsplanung_app_photon")
            loc_phot = phot.reverse((lat, lon), timeout=5, language='de')
            if loc_phot:
                props = loc_phot.raw.get('properties', {})
                p_name = props.get('name')
                p_osm_value = props.get('osm_value')
                
                if p_name and p_name not in name_parts:
                    name_parts.insert(0, p_name)
                    # Check Photon category if Nominatim was generic
                    if category == 'OTHER' and p_osm_value:
                        photon_cat_map = {
                            'restaurant': 'RESTAURANT', 'cafe': 'RESTAURANT', 'bakery': 'RESTAURANT',
                            'hotel': 'HOTEL', 'guest_house': 'HOTEL', 'apartment': 'HOTEL',
                            'beach': 'ACTIVITY', 'peak': 'ACTIVITY', 'viewpoint': 'ACTIVITY', 'cave_entrance': 'ACTIVITY'
                        }
                        if p_osm_value in photon_cat_map: category = photon_cat_map[p_osm_value]
        except: pass

        # Cleanup and Deduplicate
        clean_parts = []
        blacklist = [r"Municipal Unit of", r"Regional Unit of", r"Decentralized Administration"]
        for p in name_parts:
            p_clean = str(p)
            for pattern in blacklist:
                p_clean = re.sub(pattern, "", p_clean, flags=re.IGNORECASE).strip()
            
            if p_clean and p_clean not in clean_parts:
                if not any(p_clean.lower() in existing.lower() for existing in clean_parts):
                    clean_parts.append(p_clean)
        
        final_name = ", ".join(clean_parts[:3]) if clean_parts else "Unbekannter Ort"
        return {'name': final_name, 'category': category}

    @classmethod
    def process_raw_points(cls):
        trips = Trip.objects.filter(tracking_points__status='RAW').distinct()
        count = 0
        for trip in trips:
            count += cls._process_trip(trip)
            cls._cleanup_old_data(trip.user)
        return count
        
    @classmethod
    def _cleanup_old_data(cls, user):
        days = int(cls.get_setting(user, 'tracking_cleanup_days', '30'))
        cutoff = timezone.now() - timedelta(days=days)
        TrackingPoint.objects.filter(trip__user=user, status='PROCESSED', timestamp_utc__lt=cutoff).delete()
        TrackingSuggestion.objects.filter(user=user, is_accepted=False, created_at__lt=cutoff).delete()

    @classmethod
    def _process_trip(cls, trip):
        points = TrackingPoint.objects.filter(trip=trip, status='RAW').order_by('timestamp_local')
        if not points.exists(): return 0
        tf = TimezoneFinder()
        for p in points:
            updated = False
            if not p.timezone:
                p.timezone = tf.timezone_at(lng=float(p.lon), lat=float(p.lat))
                updated = True
            if p.timezone:
                try:
                    local_tz = pytz.timezone(p.timezone)
                    new_local_time = p.timestamp_utc.astimezone(local_tz)
                    if p.timestamp_local != new_local_time:
                        p.timestamp_local = new_local_time
                        updated = True
                except: pass
            if p.timestamp_local:
                correct_day = Day.objects.filter(trip=trip, date=p.timestamp_local.date()).first()
                if p.day != correct_day:
                    p.day = correct_day
                    updated = True
            if updated:
                p.save(update_fields=['timezone', 'timestamp_local', 'day'])
        days_map = {}
        for p in points:
            if p.day_id:
                days_map.setdefault(p.day_id, []).append(p)
        suggestions_created = 0
        stay_dist = int(cls.get_setting(trip.user, 'tracking_stay_distance', '500'))
        stay_dur = int(cls.get_setting(trip.user, 'tracking_stay_duration', '20'))
        detect_transport = cls.get_setting(trip.user, 'tracking_detect_transport', '1') == '1'
        for day_id, day_points in days_map.items():
            suggestions_created += cls._process_day_points(trip, day_id, day_points, stay_dist, stay_dur, detect_transport)
        return suggestions_created
        
    @classmethod
    def _process_day_points(cls, trip, day_id, points, stay_dist, stay_dur, detect_transport):
        if not points: return 0
        
        raw_suggestions = []
        current_cluster = []
        transport_points = []
        processed_ids = []
        last_recorded_point = None
        
        # Phase 1: Raw Clustering (Stay vs Transport)
        for point in points:
            processed_ids.append(point.id)
            if last_recorded_point and not current_cluster:
                move_dist = geodesic((last_recorded_point.lat, last_recorded_point.lon), (point.lat, point.lon)).meters
                if move_dist < 10: continue
            
            if not current_cluster:
                current_cluster.append(point)
                last_recorded_point = point
                continue
                
            first_point = current_cluster[0]
            dist = geodesic((first_point.lat, first_point.lon), (point.lat, point.lon)).meters
            
            if dist <= stay_dist:
                current_cluster.append(point)
            else:
                last_point = current_cluster[-1]
                time_gap = point.timestamp_local - last_point.timestamp_local
                time_spent = last_point.timestamp_local - first_point.timestamp_local
                
                is_stay = False
                if time_gap >= timedelta(minutes=stay_dur) or time_spent >= timedelta(minutes=stay_dur):
                    is_stay = True
                
                if is_stay:
                    if detect_transport and transport_points:
                        transport_points.append(first_point)
                        raw_suggestions.append({'type': 'TRANSPORT', 'points': list(transport_points)})
                    raw_suggestions.append({'type': 'STAY', 'points': list(current_cluster)})
                    transport_points = [last_point]
                    current_cluster = [point]
                else:
                    transport_points.extend(current_cluster)
                    current_cluster = [point]
            last_recorded_point = point
            
        # Final cluster
        if current_cluster:
            if detect_transport and transport_points:
                transport_points.append(current_cluster[0])
                raw_suggestions.append({'type': 'TRANSPORT', 'points': list(transport_points)})
            raw_suggestions.append({'type': 'STAY', 'points': list(current_cluster)})

        # Phase 2: Smarter Merging
        merged_suggestions = []
        for sug in raw_suggestions:
            if not merged_suggestions:
                merged_suggestions.append(sug)
                continue
            
            last = merged_suggestions[-1]
            
            # Merge logic for consecutive stays at the same place
            if sug['type'] == 'STAY' and last['type'] == 'STAY':
                dist = geodesic((last['points'][-1].lat, last['points'][-1].lon), (sug['points'][0].lat, sug['points'][0].lon)).meters
                if dist < stay_dist * 2: # Same area
                    last['points'].extend(sug['points'])
                    continue
            
            # Merge short transport between same-area stays
            if sug['type'] == 'STAY' and last['type'] == 'TRANSPORT' and len(merged_suggestions) >= 2:
                prev_stay = merged_suggestions[-2]
                if prev_stay['type'] == 'STAY':
                    dist = geodesic((prev_stay['points'][-1].lat, prev_stay['points'][-1].lon), (sug['points'][0].lat, sug['points'][0].lon)).meters
                    # If it's a tiny move (< 10 min) back to the "same" place, merge it all
                    move_dur = (sug['points'][0].timestamp_local - prev_stay['points'][-1].timestamp_local).total_seconds() / 60
                    if dist < stay_dist and move_dur < 15:
                        prev_stay['points'].extend(last['points'])
                        prev_stay['points'].extend(sug['points'])
                        merged_suggestions.pop() # Remove the transport
                        continue

            merged_suggestions.append(sug)

        # Phase 3: Create Database Objects
        suggestions_created = 0
        for sug in merged_suggestions:
            if sug['type'] == 'STAY':
                # Only create if it meets duration requirement after merging
                first, last = sug['points'][0], sug['points'][-1]
                dur = (last.timestamp_local - first.timestamp_local).total_seconds() / 60
                if dur >= stay_dur:
                    cls._create_stay_suggestion(trip, day_id, sug['points'])
                    suggestions_created += 1
            else:
                # Only create if it's a real transport
                if len(sug['points']) >= 2:
                    cls._create_transport_suggestion(trip, day_id, sug['points'])
                    suggestions_created += 1
                    
        TrackingPoint.objects.filter(id__in=processed_ids).update(status='PROCESSED')
        return suggestions_created

    @classmethod
    def _get_local_time(cls, point):
        if not point.timezone: return point.timestamp_local
        try:
            tz = pytz.timezone(point.timezone)
            return point.timestamp_utc.astimezone(tz)
        except: return point.timestamp_local

    @classmethod
    def _create_stay_suggestion(cls, trip, day_id, points, explicit_end_time=None):
        if not points: return
        first = points[0]
        last = points[-1]
        start_time = cls._get_local_time(first)
        end_time_local = cls._get_local_time(last) if not explicit_end_time else explicit_end_time
        
        # Prevent swapped times
        if end_time_local < start_time:
            end_time_local, start_time = start_time, end_time_local

        avg_lat = sum(float(p.lat) for p in points) / len(points)
        avg_lon = sum(float(p.lon) for p in points) / len(points)
        avg_alt = sum(int(p.alt) if p.alt else 0 for p in points) / len(points)
        
        geo_info = cls.reverse_geocode(avg_lat, avg_lon)
        place_name = geo_info['name']
        category = geo_info['category']
        
        duration_mins = int((end_time_local - start_time).total_seconds() / 60)
        
        # HEURISTICS
        suggestion_type = 'STAY'
        # 1. Hotel detection: Overnight (> 4h and spans across 03:00)
        if duration_mins > 240:
            if start_time.hour <= 3 or end_time_local.hour <= 6:
                category = 'HOTEL'
        
        # 2. Restaurant detection: Stay > 15 mins at food POI
        if category == 'RESTAURANT' and duration_mins < 15:
            category = 'OTHER' # Too short for eating

        alt_str = f" ({int(avg_alt)}m)" if avg_alt > 50 else ""
        maps_link = cls._get_maps_link(avg_lat, avg_lon)
        
        title = f"{place_name}{alt_str}"
        # Use detected category in the title for better recognition in import
        if category != 'OTHER':
            title = f"[{category}] {title}"

        notes = f'Aufenthalt von {start_time.strftime("%H:%M")} bis {end_time_local.strftime("%H:%M")} in <a href="{maps_link}" target="_blank"><b>{place_name}</b></a>.'
        
        TrackingSuggestion.objects.create(
            user=trip.user, trip=trip, day_id=day_id, title=title, suggestion_type=category if category != 'OTHER' else 'STAY',
            start_time=start_time, end_time=end_time_local, lat=avg_lat, lon=avg_lon,
            notes=notes
        )

    @classmethod
    def _create_transport_suggestion(cls, trip, day_id, points):
        if not points: return
        first = points[0]
        last = points[-1]
        start_time = cls._get_local_time(first)
        end_time = cls._get_local_time(last)
        
        # Prevent swapped times
        if end_time < start_time:
            end_time, start_time = start_time, end_time

        duration_mins = int((end_time - start_time).total_seconds() / 60)
        if duration_mins <= 0: duration_mins = 1
        
        dist_km = 0
        for i in range(1, len(points)):
            dist_km += geodesic((points[i-1].lat, points[i-1].lon), (points[i].lat, points[i].lon)).kilometers
        
        avg_speed_kmh = (dist_km / (duration_mins / 60.0)) if duration_mins > 0 else 0
        
        if avg_speed_kmh < 6: activity_type = "Spaziergang / Wanderung"
        elif avg_speed_kmh < 18: activity_type = "Jogging / Radtour"
        else: activity_type = "Fahrt"
        
        start_info = cls.reverse_geocode(first.lat, first.lon)
        dest_info = cls.reverse_geocode(last.lat, last.lon)
        
        # Distance-based naming: > 5km use only city names
        if dist_km > 5:
            # Try to extract city from geocode result (it's often the last part)
            start_short = start_info['name'].split(",")[-1].strip()
            dest_short = dest_info['name'].split(",")[-1].strip()
        else:
            start_short = start_info['name'].split(",")[0].strip()
            dest_short = dest_info['name'].split(",")[0].strip()

        start_link = cls._get_maps_link(first.lat, first.lon)
        dest_link = cls._get_maps_link(last.lat, last.lon)
        
        title = f"{activity_type} von {start_short} nach {dest_short}"
        notes = f'Von <a href="{start_link}" target="_blank"><b>{start_info["name"]}</b></a> nach <a href="{dest_link}" target="_blank"><b>{dest_info["name"]}</b></a>. Ca. {dist_km:.1f} km in {duration_mins} Minuten.'
        
        # Set event type
        final_type = 'CAR' if avg_speed_kmh >= 18 else 'ACTIVITY'

        TrackingSuggestion.objects.create(
            user=trip.user, trip=trip, day_id=day_id, title=title, suggestion_type=final_type,
            start_time=start_time, end_time=end_time, lat=last.lat, lon=last.lon,
            notes=notes, distance_km=dist_km
        )
