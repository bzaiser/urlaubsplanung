import logging
from datetime import timedelta
from django.utils import timezone
from geopy.distance import geodesic
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
    def process_raw_points(cls):
        """Processes all RAW tracking points and generates suggestions."""
        trips = Trip.objects.filter(tracking_points__status='RAW').distinct()
        
        count = 0
        for trip in trips:
            count += cls._process_trip(trip)
            
            # Run cleanup per user based on their settings
            cls._cleanup_old_data(trip.user)
            
        return count
        
    @classmethod
    def _cleanup_old_data(cls, user):
        days = int(cls.get_setting(user, 'tracking_cleanup_days', '30'))
        cutoff = timezone.now() - timedelta(days=days)
        
        # Delete old processed tracking points
        TrackingPoint.objects.filter(
            trip__user=user, 
            status='PROCESSED', 
            timestamp_utc__lt=cutoff
        ).delete()
        
        # Delete old unaccepted suggestions
        TrackingSuggestion.objects.filter(
            user=user, 
            is_accepted=False, 
            created_at__lt=cutoff
        ).delete()

    @classmethod
    def _process_trip(cls, trip):
        points = TrackingPoint.objects.filter(
            trip=trip, 
            status='RAW'
        ).order_by('timestamp_local')
        
        if not points.exists():
            return 0
            
        # Group by day
        days_map = {}
        for p in points:
            if p.day_id:
                days_map.setdefault(p.day_id, []).append(p)
                
        suggestions_created = 0
        
        stay_dist = int(cls.get_setting(trip.user, 'tracking_stay_distance', '150'))
        stay_dur = int(cls.get_setting(trip.user, 'tracking_stay_duration', '20'))
        detect_transport = cls.get_setting(trip.user, 'tracking_detect_transport', '1') == '1'
        
        for day_id, day_points in days_map.items():
            suggestions_created += cls._process_day_points(trip, day_id, day_points, stay_dist, stay_dur, detect_transport)
            
        return suggestions_created
        
    @classmethod
    def _process_day_points(cls, trip, day_id, points, stay_dist, stay_dur, detect_transport):
        if not points:
            return 0
            
        suggestions_created = 0
        transport_points = []
        current_cluster = []
        
        for point in points:
            point.status = 'PROCESSED'
            point.save()
            
            if not current_cluster:
                current_cluster.append(point)
                continue
                
            first_point = current_cluster[0]
            dist = geodesic(
                (first_point.lat, first_point.lon),
                (point.lat, point.lon)
            ).meters
            
            if dist <= stay_dist:
                current_cluster.append(point)
            else:
                time_spent = current_cluster[-1].timestamp_local - first_point.timestamp_local
                if time_spent >= timedelta(minutes=stay_dur):
                    if detect_transport and len(transport_points) >= 2:
                        cls._create_transport_suggestion(trip, day_id, transport_points)
                        suggestions_created += 1
                        transport_points = []
                    
                    cls._create_stay_suggestion(trip, day_id, current_cluster)
                    suggestions_created += 1
                    current_cluster = [point]
                else:
                    transport_points.extend(current_cluster)
                    current_cluster = [point]
                
        # End of day cleanup
        if current_cluster:
            time_spent = current_cluster[-1].timestamp_local - current_cluster[0].timestamp_local
            if time_spent >= timedelta(minutes=stay_dur):
                if detect_transport and len(transport_points) >= 2:
                    cls._create_transport_suggestion(trip, day_id, transport_points)
                    suggestions_created += 1
                cls._create_stay_suggestion(trip, day_id, current_cluster)
                suggestions_created += 1
            else:
                transport_points.extend(current_cluster)
                # Only create transport if it spans more than a few minutes or some distance
                if detect_transport and len(transport_points) >= 2:
                    total_dur = transport_points[-1].timestamp_local - transport_points[0].timestamp_local
                    if total_dur >= timedelta(minutes=5):
                        cls._create_transport_suggestion(trip, day_id, transport_points)
                        suggestions_created += 1
                
        return suggestions_created

    @classmethod
    def _create_stay_suggestion(cls, trip, day_id, points):
        if not points: return
        first = points[0]
        last = points[-1]
        
        avg_lat = sum(float(p.lat) for p in points) / len(points)
        avg_lon = sum(float(p.lon) for p in points) / len(points)
        
        duration_mins = int((last.timestamp_local - first.timestamp_local).total_seconds() / 60)
        title = f"Aufenthalt ({duration_mins} Min)"
        
        TrackingSuggestion.objects.create(
            user=trip.user,
            trip=trip,
            day_id=day_id,
            title=title,
            suggestion_type='STAY',
            start_time=first.timestamp_local,
            end_time=last.timestamp_local,
            lat=avg_lat,
            lon=avg_lon,
            notes=f"Automatisch erkannter Aufenthalt von {first.timestamp_local.strftime('%H:%M')} bis {last.timestamp_local.strftime('%H:%M')}."
        )

    @classmethod
    def _create_transport_suggestion(cls, trip, day_id, points):
        if not points: return
        first = points[0]
        last = points[-1]
        
        duration_mins = int((last.timestamp_local - first.timestamp_local).total_seconds() / 60)
        
        # Calculate rough distance
        dist_km = 0
        for i in range(1, len(points)):
            dist_km += geodesic(
                (points[i-1].lat, points[i-1].lon),
                (points[i].lat, points[i].lon)
            ).kilometers
            
        title = f"Fahrt/Bewegung ({dist_km:.1f} km)"
        
        TrackingSuggestion.objects.create(
            user=trip.user,
            trip=trip,
            day_id=day_id,
            title=title,
            suggestion_type='TRANSPORT',
            start_time=first.timestamp_local,
            end_time=last.timestamp_local,
            lat=last.lat, # Mark the end of the trip
            lon=last.lon,
            notes=f"Zurückgelegte Distanz: ca. {dist_km:.1f} km in {duration_mins} Minuten (Start: {first.timestamp_local.strftime('%H:%M')}, Ende: {last.timestamp_local.strftime('%H:%M')})."
        )
