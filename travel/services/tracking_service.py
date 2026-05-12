import logging
import time
import re
from datetime import timedelta
from django.utils import timezone
from geopy.distance import geodesic
from geopy.geocoders import Nominatim
from travel.models import TrackingPoint, TrackingSuggestion, Trip, GlobalSetting

logger = logging.getLogger(__name__)

class TrackingProcessor:
    
    @classmethod
    def get_setting(cls, user, key, default):
        s = GlobalSetting.objects.filter(user=user, key=key).first()
        if s and s.value.strip():
            return s.value.strip()
        return default

    @classmethod
    def reverse_geocode(cls, lat, lon):
        try:
            geolocator = Nominatim(user_agent="urlaubsplanung_app")
            # Force language to German/English
            location = geolocator.reverse((lat, lon), timeout=10, language='de,en')
            if location:
                raw = location.raw
                address = raw.get('address', {})
                
                # 1. Try to find a real name (POI)
                poi_keys = [
                    'amenity', 'tourism', 'historic', 'shop', 'leisure', 'office', 'craft',
                    'restaurant', 'cafe', 'hotel', 'museum', 'attraction', 'viewpoint', 
                    'castle', 'monument', 'marina', 'pier', 'park', 'supermarket', 'mall'
                ]
                
                name = None
                for key in poi_keys:
                    if key in address:
                        name = address[key]
                        break
                
                # 2. Get specific location parts
                suburb = address.get('suburb') or address.get('city_district') or address.get('neighbourhood')
                road = address.get('road')
                city = address.get('city') or address.get('town') or address.get('village')
                
                # 3. Handle administrative names as last resort
                # If we only have administrative names, they often contain "Municipal Unit" etc.
                admin_name = address.get('municipality') or address.get('county')
                
                # 4. Filter out bureaucratic terms
                blacklist = [
                    r"Municipal Unit of", r"Regional Unit of", r"Gemeinde", r"Präfektur", 
                    r"Regionalbezirk", r"Dimos", r"Decentralized Administration"
                ]
                
                parts = []
                if name: parts.append(name)
                if road: parts.append(road)
                if suburb: parts.append(suburb)
                if city: parts.append(city)
                if not parts and admin_name: parts.append(admin_name)
                
                clean_parts = []
                for p in parts:
                    p_clean = str(p)
                    for pattern in blacklist:
                        p_clean = re.sub(pattern, "", p_clean, flags=re.IGNORECASE).strip()
                    
                    # Deduplicate and avoid adding empty strings
                    if p_clean and p_clean not in clean_parts:
                        # Avoid adding "Pythagoreio" if "Pythagorio" is already there (fuzzy)
                        is_duplicate = False
                        for existing in clean_parts:
                            if p_clean.lower() in existing.lower() or existing.lower() in p_clean.lower():
                                is_duplicate = True
                                break
                        if not is_duplicate:
                            clean_parts.append(p_clean)
                
                if clean_parts:
                    return ", ".join(clean_parts[:2]) # Max 2 parts for brevity
                
                return location.address.split(",")[0]
        except Exception as e:
            logger.error(f"Geocoding error: {e}")
        return None

    @classmethod
    def process_raw_points(cls):
        """Processes all RAW tracking points and generates suggestions."""
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
    def _create_stay_suggestion(cls, trip, day_id, points, explicit_end_time=None):
        if not points: return
        first = points[0]
        last = points[-1]
        end_time = explicit_end_time or last.timestamp_local
        avg_lat = sum(float(p.lat) for p in points) / len(points)
        avg_lon = sum(float(p.lon) for p in points) / len(points)
        place_name = cls.reverse_geocode(avg_lat, avg_lon)
        duration_mins = int((end_time - first.timestamp_local).total_seconds() / 60)
        title = place_name or f"Aufenthalt ({duration_mins} Min)"
        TrackingSuggestion.objects.create(
            user=trip.user, trip=trip, day_id=day_id, title=title, suggestion_type='STAY',
            start_time=first.timestamp_local, end_time=end_time, lat=avg_lat, lon=avg_lon,
            notes=f"Aufenthalt in {place_name if place_name else 'diesem Ort'} von {first.timestamp_local.strftime('%H:%M')} bis {end_time.strftime('%H:%M')}."
        )

    @classmethod
    def _create_transport_suggestion(cls, trip, day_id, points):
        if not points: return
        first = points[0]
        last = points[-1]
        duration_mins = int((last.timestamp_local - first.timestamp_local).total_seconds() / 60)
        if duration_mins <= 0: duration_mins = 1
        dist_km = 0
        for i in range(1, len(points)):
            dist_km += geodesic((points[i-1].lat, points[i-1].lon), (points[i].lat, points[i].lon)).kilometers
        
        avg_speed_kmh = (dist_km / (duration_mins / 60.0))
        if avg_speed_kmh < 7: activity_type = "Spaziergang / Wanderung"
        elif avg_speed_kmh < 15: activity_type = "Jogging / Radtour"
        else: activity_type = "Fahrt"

        dest_name = cls.reverse_geocode(last.lat, last.lon)
        if dest_name:
            dest_short = dest_name.split(",")[0]
            title = f"{activity_type} nach {dest_short}"
        else:
            title = f"{activity_type} ({dist_km:.1f} km)"
        
        TrackingSuggestion.objects.create(
            user=trip.user, trip=trip, day_id=day_id, title=title, suggestion_type='TRANSPORT',
            start_time=first.timestamp_local, end_time=last.timestamp_local, lat=last.lat, lon=last.lon,
            notes=f"{activity_type}: ca. {dist_km:.1f} km in {duration_mins} Minuten nach {dest_name if dest_name else 'Zielort'}. (Schnitt: {avg_speed_kmh:.1f} km/h)"
        )
