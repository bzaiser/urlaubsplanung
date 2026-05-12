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
        try:
            geolocator = Nominatim(user_agent="urlaubsplanung_app_v3")
            location = geolocator.reverse((lat, lon), timeout=10, language='de,en', zoom=18)
            if location:
                raw = location.raw
                address = raw.get('address', {})
                
                # Garbage words to remove
                blacklist = [
                    r"Municipal Unit of", r"Regional Unit of", r"Gemeinde", 
                    r"Präfektur", r"Regionalbezirk", r"Dimos", 
                    r"Decentralized Administration", r"Region of"
                ]

                def clean_text(text):
                    if not text: return ""
                    t = str(text)
                    for pattern in blacklist:
                        t = re.sub(pattern, "", t, flags=re.IGNORECASE).strip()
                    return t

                # Priority for specific POIs
                poi_keys = [
                    'beach', 'tourism', 'amenity', 'leisure', 'historic', 'shop', 
                    'restaurant', 'cafe', 'hotel', 'museum', 'attraction', 'viewpoint', 
                    'castle', 'monument', 'marina', 'pier', 'park', 'natural', 'peak'
                ]
                
                name = None
                for key in poi_keys:
                    if key in address:
                        name = clean_text(address[key])
                        break
                
                if not name:
                    display_parts = location.address.split(",")
                    if len(display_parts) > 0:
                        potential = clean_text(display_parts[0])
                        # Check if it's just a house number or broad city
                        if not potential.isdigit():
                            name = potential

                city = clean_text(address.get('city') or address.get('town') or address.get('village'))
                road = clean_text(address.get('road'))
                
                # Build result parts with deduplication
                result_parts = []
                if name: result_parts.append(name)
                
                if road and road not in result_parts:
                    # Check if road is not just a substring of name
                    if not any(road.lower() in r.lower() for r in result_parts):
                        result_parts.append(road)
                
                if city and city not in result_parts:
                    if not any(city.lower() in r.lower() for r in result_parts):
                        result_parts.append(city)
                
                # If we have too many parts, focus on the most specific ones
                if len(result_parts) > 2:
                    return ", ".join(result_parts[:2])
                
                return ", ".join(result_parts) if result_parts else location.address.split(",")[0]
        except Exception as e:
            logger.error(f"Geocoding error: {e}")
        return None

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
        suggestions_created = 0
        transport_points = []
        current_cluster = []
        processed_ids = []
        last_recorded_point = None
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
                time_spent_in_cluster = last_point.timestamp_local - first_point.timestamp_local
                is_stay = False
                end_time = last_point.timestamp_local
                if time_gap >= timedelta(minutes=stay_dur):
                    is_stay = True
                    end_time = point.timestamp_local
                elif time_spent_in_cluster >= timedelta(minutes=stay_dur):
                    is_stay = True
                if is_stay:
                    if detect_transport and transport_points:
                        transport_points.append(first_point)
                        cls._create_transport_suggestion(trip, day_id, transport_points)
                        suggestions_created += 1
                        time.sleep(1) 
                    cls._create_stay_suggestion(trip, day_id, current_cluster, explicit_end_time=end_time)
                    suggestions_created += 1
                    time.sleep(1)
                    transport_points = [last_point]
                    current_cluster = [point]
                else:
                    transport_points.extend(current_cluster)
                    current_cluster = [point]
            last_recorded_point = point
        if current_cluster:
            last_point = current_cluster[-1]
            first_point = current_cluster[0]
            time_spent_in_cluster = last_point.timestamp_local - first_point.timestamp_local
            if time_spent_in_cluster >= timedelta(minutes=stay_dur):
                if detect_transport and transport_points:
                    transport_points.append(first_point)
                    cls._create_transport_suggestion(trip, day_id, transport_points)
                    suggestions_created += 1
                    time.sleep(1)
                cls._create_stay_suggestion(trip, day_id, current_cluster)
                suggestions_created += 1
            else:
                transport_points.extend(current_cluster)
                if detect_transport and len(transport_points) >= 2:
                    total_dur = transport_points[-1].timestamp_local - transport_points[0].timestamp_local
                    if total_dur >= timedelta(minutes=5):
                        cls._create_transport_suggestion(trip, day_id, transport_points)
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
        avg_lat = sum(float(p.lat) for p in points) / len(points)
        avg_lon = sum(float(p.lon) for p in points) / len(points)
        avg_alt = sum(int(p.alt) if p.alt else 0 for p in points) / len(points)
        place_name = cls.reverse_geocode(avg_lat, avg_lon)
        alt_str = f" ({int(avg_alt)}m)" if avg_alt > 50 else ""
        duration_mins = int((end_time_local - start_time).total_seconds() / 60)
        
        maps_link = cls._get_maps_link(avg_lat, avg_lon)
        # Plain text title as requested
        title = f"{place_name if place_name else 'Aufenthalt'}{alt_str}"
        # Links only in the NOTES (for WYSIWYG editor)
        notes = f'Aufenthalt von {start_time.strftime("%H:%M")} bis {end_time_local.strftime("%H:%M")} in <a href="{maps_link}" target="_blank"><b>{place_name}</b></a>.'
        
        TrackingSuggestion.objects.create(
            user=trip.user, trip=trip, day_id=day_id, title=title, suggestion_type='STAY',
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
        duration_mins = int((end_time - start_time).total_seconds() / 60)
        if duration_mins <= 0: duration_mins = 1
        dist_km = 0
        for i in range(1, len(points)):
            dist_km += geodesic((points[i-1].lat, points[i-1].lon), (points[i].lat, points[i].lon)).kilometers
        avg_speed_kmh = (dist_km / (duration_mins / 60.0))
        if avg_speed_kmh < 7: activity_type = "Spaziergang / Wanderung"
        elif avg_speed_kmh < 15: activity_type = "Jogging / Radtour"
        else: activity_type = "Fahrt"
        start_name = cls.reverse_geocode(first.lat, first.lon)
        dest_name = cls.reverse_geocode(last.lat, last.lon)
        start_short = start_name.split(",")[0] if start_name else "Start"
        dest_short = dest_name.split(",")[0] if dest_name else "Ziel"
        start_link = cls._get_maps_link(first.lat, first.lon)
        dest_link = cls._get_maps_link(last.lat, last.lon)
        
        # Plain text title as requested
        title = f"{activity_type} von {start_short} nach {dest_short}"
        # Links only in the NOTES (for WYSIWYG editor)
        notes = f'Von <a href="{start_link}" target="_blank"><b>{start_short}</b></a> nach <a href="{dest_link}" target="_blank"><b>{dest_short}</b></a>. Ca. {dist_km:.1f} km in {duration_mins} Minuten.'
        
        TrackingSuggestion.objects.create(
            user=trip.user, trip=trip, day_id=day_id, title=title, suggestion_type='TRANSPORT',
            start_time=start_time, end_time=end_time, lat=last.lat, lon=last.lon,
            notes=notes
        )
