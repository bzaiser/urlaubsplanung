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
    _geocode_cache = {}

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
    def _clear_cache(cls):
        cls._geocode_cache = {}

    @classmethod
    def reverse_geocode(cls, lat, lon, fast=False):
        from geopy.geocoders import Photon, Nominatim
        
        # Cache check
        cache_key = (round(float(lat), 5), round(float(lon), 5), fast)
        if cache_key in cls._geocode_cache:
            return cls._geocode_cache[cache_key]

        name_parts = []
        category = 'OTHER'
        
        # 1. Try Nominatim ONLY if NOT in fast mode
        if not fast:
            try:
                time.sleep(1) # Respect rate limits
                nom = Nominatim(user_agent="urlaubsplanung_app_v5_9")
                loc_nom = nom.reverse((lat, lon), timeout=5, language='de,en;q=0.5', zoom=18)
                if loc_nom:
                    addr = loc_nom.raw.get('address', {})
                    dist = geodesic((lat, lon), (loc_nom.latitude, loc_nom.longitude)).meters
                    is_far = dist > 50
                    cat_map = {
                        'hotel': 'HOTEL', 'guest_house': 'HOTEL', 'apartment': 'HOTEL', 'hostel': 'HOTEL', 'bungalow': 'HOTEL',
                        'camping_site': 'CAMPING', 'caravan_site': 'CAMPING', 'restaurant': 'RESTAURANT', 'cafe': 'RESTAURANT',
                        'peak': 'ACTIVITY', 'beach': 'ACTIVITY', 'viewpoint': 'ACTIVITY', 'attraction': 'ACTIVITY',
                        'museum': 'ACTIVITY', 'historic': 'ACTIVITY', 'castle': 'ACTIVITY', 'parking': 'STAY'
                    }
                    poi_keys = ['hotel', 'guest_house', 'apartment', 'bungalow', 'restaurant', 'cafe', 'peak', 'beach', 'attraction', 'museum', 'historic', 'castle', 'parking', 'amenity', 'tourism']
                    for key in poi_keys:
                        if key in addr and not is_far:
                            val = addr[key]
                            if val not in name_parts:
                                if key == 'peak': val = f"Gipfel: {val}"
                                elif key == 'parking': val = f"Parkplatz {val}" if val != "yes" else "Parkplatz"
                                elif key == 'castle': val = f"Burg/Schloss: {val}"
                                name_parts.append(val)
                            if key in cat_map: category = cat_map[key]
                            break
                    road = addr.get('road')
                    house_number = addr.get('house_number')
                    city = addr.get('city') or addr.get('town') or addr.get('village')
                    if road:
                        street = f"{road} {house_number}".strip() if house_number else road
                        if street not in name_parts: name_parts.append(street)
                    if city and city not in name_parts: name_parts.append(city)
            except Exception as e:
                logger.warning(f"Nominatim Error: {e}")

        # 2. Try Photon as fallback (or as primary in fast mode)
        if len(name_parts) < 1:
            try:
                phot = Photon(user_agent="urlaubsplanung_app_photon_v5_9")
                loc_phot = phot.reverse((lat, lon), timeout=3, language='de')
                if loc_phot:
                    dist = geodesic((lat, lon), (loc_phot.latitude, loc_phot.longitude)).meters
                    if dist < 60:
                        props = loc_phot.raw.get('properties', {})
                        p_name = props.get('name')
                        if p_name and p_name not in name_parts:
                            name_parts.insert(0, p_name)
                            if category == 'OTHER':
                                p_val = props.get('osm_value')
                                if p_val in ['hotel', 'apartment', 'guest_house']: category = 'HOTEL'
                                elif p_val in ['restaurant', 'cafe']: category = 'RESTAURANT'
                    if len(name_parts) < 1 and loc_phot.address:
                        name_parts.append(loc_phot.address.split(",")[0])
            except Exception as e:
                logger.warning(f"Photon Error: {e}")

        # Cleanup and Transliteration
        clean_parts = []
        admin_patterns = [r"Municipal Unit of\s*", r"Regional Unit of\s*", r"Decentralized Administration of\s*", r"Prefecture of\s*", r"Region of\s*", r"Community of\s*"]
        for p in name_parts:
            p_clean = str(p)
            for pattern in admin_patterns: p_clean = re.sub(pattern, "", p_clean, flags=re.IGNORECASE).strip()
            if any(ord(c) > 127 for c in p_clean): p_clean = cls._transliterate_greek(p_clean)
            if p_clean and p_clean not in clean_parts:
                if not any(p_clean.lower() in existing.lower() for existing in clean_parts): clean_parts.append(p_clean)
        
        final_name = ", ".join(clean_parts[:3]) if clean_parts else "Unbekannter Ort"
        result = {'name': final_name, 'category': category}
        cls._geocode_cache[cache_key] = result
        return result
    @classmethod
    def _transliterate_greek(cls, text):
        """Simple mapping to transliterate Greek characters to Latin if needed."""
        greek_to_latin = {
            'Α': 'A', 'Β': 'B', 'Γ': 'G', 'Δ': 'D', 'Ε': 'E', 'Ζ': 'Z', 'Η': 'H', 'Θ': 'Th', 'Ι': 'I', 'Κ': 'K', 'Λ': 'L', 'Μ': 'M', 'Ν': 'N', 'Ξ': 'X', 'Ο': 'O', 'Π': 'P', 'Ρ': 'R', 'Σ': 'S', 'Τ': 'T', 'Υ': 'Y', 'Φ': 'Ph', 'Χ': 'Ch', 'Ψ': 'Ps', 'Ω': 'O',
            'α': 'a', 'β': 'b', 'γ': 'g', 'δ': 'd', 'ε': 'e', 'ζ': 'z', 'η': 'h', 'θ': 'th', 'ι': 'i', 'κ': 'k', 'λ': 'l', 'μ': 'm', 'ν': 'n', 'ξ': 'x', 'ο': 'o', 'π': 'p', 'ρ': 'r', 'σ': 's', 'τ': 't', 'υ': 'y', 'φ': 'ph', 'χ': 'ch', 'ψ': 'ps', 'ω': 'o', 'ς': 's',
            'ά': 'a', 'έ': 'e', 'ή': 'h', 'ί': 'i', 'ό': 'o', 'ύ': 'y', 'ώ': 'o', 'ϊ': 'i', 'ϋ': 'y', 'ΐ': 'i', 'ΰ': 'y'
        }
        return "".join(greek_to_latin.get(c, c) for c in text)

    @classmethod
    def process_raw_points(cls):
        """
        Processes raw tracking points. 
        Returns (suggestions_created, has_more_data_bool)
        This version processes only ONE day per call to avoid timeouts.
        """
        cls._clear_cache()
        # Find the first trip that has any RAW points
        trip = Trip.objects.filter(tracking_points__status='RAW').first()
        if not trip:
            return 0, False

        # Get all RAW points for this trip
        raw_points = TrackingPoint.objects.filter(trip=trip, status='RAW').order_by('timestamp_local')
        if not raw_points.exists():
            return 0, False

        # Group them by day (using the date of the first point)
        first_point = raw_points.first()
        # Ensure we have timezone/day info for the points of this first date
        # We process ALL points for this specific date in this trip
        target_date = first_point.timestamp_local.date() if first_point.timestamp_local else first_point.timestamp_utc.date()
        
        # Filter points for this specific trip and date
        # We need to be careful with timezone shifts, so we use a range
        day_points = []
        other_points_exist = False
        
        # Quick update of timezone/day for the next batch to identify the day correctly
        # But for efficiency, we just take the first ~500 points or so that belong to the same "cluster"
        current_day_points = []
        next_day_point = None
        for p in raw_points:
            p_date = p.timestamp_local.date() if p.timestamp_local else p.timestamp_utc.date()
            if not current_day_points or p_date == target_date:
                current_day_points.append(p)
                target_date = p_date # Update target date if it was null
            else:
                next_day_point = p
                other_points_exist = True
                break
        
        # Process this day
        suggestions_created = cls._process_trip_subset(trip, current_day_points, next_day_point=next_day_point)
        
        # Check if there's more after this
        if not other_points_exist:
            # Check other trips
            other_points_exist = Trip.objects.filter(tracking_points__status='RAW').exclude(id=trip.id).exists()

        return suggestions_created, other_points_exist

    @classmethod
    def _process_trip_subset(cls, trip, points, next_day_point=None):
        if not points: return 0
        tf = TimezoneFinder()
        
        # Prepare timezone info for all points in batch + next point
        check_points = list(points)
        if next_day_point:
            check_points.append(next_day_point)
            
        for p in check_points:
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
            # Group by day_id if exists, otherwise by local date (fallback)
            group_key = f"day_{p.day_id}" if p.day_id else f"date_{p.timestamp_local.date()}"
            days_map.setdefault(group_key, []).append(p)
        
        suggestions_created = 0
        stay_dist = int(cls.get_setting(trip.user, 'tracking_stay_distance', '500'))
        stay_dur = int(cls.get_setting(trip.user, 'tracking_stay_duration', '20'))
        detect_transport = cls.get_setting(trip.user, 'tracking_detect_transport', '1') == '1'
        
        for group_key, day_points in days_map.items():
            # Extract day_id if it's a day_ key
            current_day_id = int(group_key.split("_")[1]) if group_key.startswith("day_") else None
            suggestions_created += cls._process_day_points(trip, current_day_id, day_points, stay_dist, stay_dur, detect_transport, next_day_point=next_day_point)
            cls._cleanup_old_data(trip.user)
        
        # CRITICAL: Mark all points in this batch as PROCESSED, even if they didn't match a Day
        # otherwise we get stuck in an infinite loop for points outside the trip range.
        TrackingPoint.objects.filter(id__in=[p.id for p in points]).update(status='PROCESSED')
            
        return suggestions_created

    @classmethod
    def _cleanup_old_data(cls, user):
        days = int(cls.get_setting(user, 'tracking_cleanup_days', '30'))
        cutoff = timezone.now() - timedelta(days=days)
        TrackingPoint.objects.filter(trip__user=user, status='PROCESSED', timestamp_utc__lt=cutoff).delete()
        TrackingSuggestion.objects.filter(user=user, is_accepted=False, created_at__lt=cutoff).delete()

    @classmethod
    def _get_local_time(cls, point):
        if not point.timezone: return point.timestamp_local
        try:
            tz = pytz.timezone(point.timezone)
            return point.timestamp_utc.astimezone(tz)
        except: return point.timestamp_local

    @classmethod
    def _process_day_points(cls, trip, day_id, points, stay_dist, stay_dur, detect_transport, next_day_point=None):
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
                    # Stretch the stay until the current point (the one that triggered the move)
                    raw_suggestions.append({
                        'type': 'STAY', 
                        'points': list(current_cluster),
                        'explicit_end_time': point.timestamp_local
                    })
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
            
            # Stretch the final stay of the day to the first point of the next day if available
            explicit_end = None
            if next_day_point:
                explicit_end = next_day_point.timestamp_local
                
            raw_suggestions.append({
                'type': 'STAY', 
                'points': list(current_cluster),
                'explicit_end_time': explicit_end
            })

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
        
        geo_info = cls.reverse_geocode(avg_lat, avg_lon)
        place_name = geo_info['name']
        category = geo_info['category']
        
        duration_mins = int((end_time_local - start_time).total_seconds() / 60)
        
        # --- SMART CONTEXT LOGIC 5.4 ---
        # 1. Detect Midnight/Overnight
        is_midnight_start = start_time.hour == 0 and start_time.minute <= 30 and duration_mins > 120
        is_midnight_end = end_time_local.hour == 23 and end_time_local.minute >= 30 and duration_mins > 120
        is_classic_overnight = duration_mins > 240 and (start_time.hour <= 3 or end_time_local.hour >= 5)
        
        context = 'GENERAL'
        if is_midnight_start or is_midnight_end or is_classic_overnight:
            category = 'HOTEL'
            context = 'LODGING'
        elif (11 <= start_time.hour <= 14) or (18 <= start_time.hour <= 21):
            if category == 'RESTAURANT' or duration_mins > 30:
                context = 'FOOD'
        elif duration_mins > 60:
            # Nature vs Culture based on name hints or remote location (simple heuristic)
            if any(x in place_name.lower() for x in ['berg', 'gipfel', 'strand', 'beach', 'peak', 'wald']):
                context = 'NATURE'
            else:
                context = 'CULTURE'

        # Special POI Search based on context
        special_poi = cls._find_special_poi(avg_lat, avg_lon, context)
        if special_poi:
            place_name = special_poi

        maps_link = cls._get_maps_link(avg_lat, avg_lon)
        
        # Sampling (FAST mode)
        unique_pois = []
        last_sampled_point = first
        for p in points:
            if geodesic((last_sampled_point.lat, last_sampled_point.lon), (p.lat, p.lon)).meters > 300:
                p_info = cls.reverse_geocode(p.lat, p.lon, fast=True)
                p_name = p_info['name'].split(",")[0]
                if p_name not in unique_pois and p_name != "Unbekannter Ort" and p_name != place_name.split(",")[0]:
                    unique_pois.append(p_name)
                last_sampled_point = p
        
        # Final Title
        if category == 'HOTEL':
            title = f"Übernachtung in {place_name.split(',')[0]}"
        elif category == 'RESTAURANT' or context == 'FOOD':
            title = f"Essen in {place_name.split(',')[0]}"
            category = 'RESTAURANT'
        elif category == 'ACTIVITY' or context in ['NATURE', 'CULTURE']:
            title = place_name
            if len(unique_pois) > 1:
                title = f"Besichtigung / Wanderung in {place_name.split(',')[-1].strip()}"
            category = 'ACTIVITY'
        else:
            title = place_name
        
        from django.utils import timezone as django_timezone
        notes_start = django_timezone.localtime(start_time).strftime("%H:%M")
        notes_end = django_timezone.localtime(end_time_local).strftime("%H:%M")
        notes = f'Aufenthalt von {notes_start} bis {notes_end} in <a href="{maps_link}" target="_blank"><b>{place_name}</b></a>.'

        TrackingSuggestion.objects.create(
            user=trip.user, trip=trip, day_id=day_id, title=title, 
            suggestion_type=category if category != 'OTHER' else 'STAY',
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
        
        if end_time < start_time:
            end_time, start_time = start_time, end_time

        duration_mins = int((end_time - start_time).total_seconds() / 60)
        if duration_mins <= 0: duration_mins = 1
        
        dist_km = 0
        for i in range(1, len(points)):
            dist_km += geodesic((points[i-1].lat, points[i-1].lon), (points[i].lat, points[i].lon)).kilometers
        
        avg_speed_kmh = (dist_km / (duration_mins / 60.0)) if duration_mins > 0 else 0
        
        # --- TRANSPORT HEURISTICS 4.1 (Distance Enforcement) ---
        if dist_km > 10:
            # More than 10km is always a CAR drive unless speed is incredibly low (< 3kmh)
            if avg_speed_kmh > 3:
                activity_type = "Fahrt"
                final_type = 'CAR'
            else:
                activity_type = "Lange Wanderung"
                final_type = 'ACTIVITY'
        elif avg_speed_kmh > 15:
            activity_type = "Fahrt"
            final_type = 'CAR'
        elif avg_speed_kmh > 6:
            activity_type = "Radtour / Jogging"
            final_type = 'ACTIVITY'
        else:
            activity_type = "Spaziergang / Wanderung"
            final_type = 'ACTIVITY'
        
        start_info = cls.reverse_geocode(first.lat, first.lon, fast=True)
        dest_info = cls.reverse_geocode(last.lat, last.lon, fast=True)
        
        if dist_km > 5:
            start_short = start_info['name'].split(",")[-1].strip()
            dest_short = dest_info['name'].split(",")[-1].strip()
        else:
            start_short = start_info['name'].split(",")[0].strip()
            dest_short = dest_info['name'].split(",")[0].strip()

        start_link = cls._get_maps_link(first.lat, first.lon)
        dest_link = cls._get_maps_link(last.lat, last.lon)
        
        title = f"{activity_type} von {start_short} nach {dest_short}"
        notes = f'Von <a href="{start_link}" target="_blank"><b>{start_info["name"]}</b></a> nach <a href="{dest_link}" target="_blank"><b>{dest_info["name"]}</b></a>. Ca. {dist_km:.1f} km in {duration_mins} Minuten.'
        
        TrackingSuggestion.objects.create(
            user=trip.user, trip=trip, day_id=day_id, title=title, suggestion_type=final_type,
            start_time=start_time, end_time=end_time, lat=last.lat, lon=last.lon,
            notes=notes, distance_km=dist_km
        )
    @classmethod
    def _find_special_poi(cls, lat, lon, context):
        """Tries to find a POI matching context near the given location."""
        queries = {
            'LODGING': "hotel,apartment,guest house,bungalow,villa,camp_site",
            'FOOD': "restaurant,cafe,tavern,pub,bar",
            'NATURE': "peak,beach,viewpoint,natural",
            'CULTURE': "attraction,historic,museum,castle,church,monument",
            'GENERAL': "tourism,amenity"
        }
        query = queries.get(context, "tourism,amenity")
        
        try:
            from geopy.geocoders import Photon
            geolocator = Photon()
            locations = geolocator.geocode(query, proximity=(lat, lon), limit=5, exactly_one=False, language='de')
            
            if locations:
                for loc in locations:
                    dist = geodesic((lat, lon), (loc.latitude, loc.longitude)).meters
                    if dist < 120:
                        name = loc.address.split(",")[0]
                        # Clean prefix if already present in result
                        if context == 'NATURE' and any(x in str(loc.raw).lower() for x in ['peak', 'natural=peak']):
                            return f"Gipfel: {name}"
                        return name
        except: pass
        return None
