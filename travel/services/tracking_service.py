import logging
from datetime import timedelta
from django.utils import timezone
from geopy.distance import geodesic
from travel.models import TrackingPoint, TrackingSuggestion, Trip

logger = logging.getLogger(__name__)

class TrackingProcessor:
    STAY_DISTANCE_METERS = 150  # Radius for a single stay
    STAY_DURATION_MINUTES = 20  # Minimum time to be considered a stay
    
    @classmethod
    def process_raw_points(cls):
        """Processes all RAW tracking points and generates suggestions."""
        # Find trips that have raw points
        trips = Trip.objects.filter(tracking_points__status='RAW').distinct()
        
        count = 0
        for trip in trips:
            count += cls._process_trip(trip)
            
        return count
        
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
        
        for day_id, day_points in days_map.items():
            suggestions_created += cls._process_day_points(trip, day_id, day_points)
            
        return suggestions_created
        
    @classmethod
    def _process_day_points(cls, trip, day_id, points):
        """
        Simple clustering algorithm:
        Iterate through points chronologically.
        If the next point is within STAY_DISTANCE_METERS, we are still at the same stay.
        If the duration exceeds STAY_DURATION_MINUTES, record it as a STAY suggestion.
        """
        if not points:
            return 0
            
        suggestions_created = 0
        current_stay_points = []
        
        for point in points:
            # Mark point as processed immediately
            point.status = 'PROCESSED'
            point.save()
            
            if not current_stay_points:
                current_stay_points.append(point)
                continue
                
            first_point = current_stay_points[0]
            
            # Check distance to the start of the current stay cluster
            dist = geodesic(
                (first_point.lat, first_point.lon),
                (point.lat, point.lon)
            ).meters
            
            if dist <= cls.STAY_DISTANCE_METERS:
                current_stay_points.append(point)
            else:
                # We moved away from the cluster. Was it a stay?
                time_spent = current_stay_points[-1].timestamp_local - first_point.timestamp_local
                if time_spent >= timedelta(minutes=cls.STAY_DURATION_MINUTES):
                    cls._create_stay_suggestion(trip, day_id, current_stay_points)
                    suggestions_created += 1
                
                # Start new cluster
                current_stay_points = [point]
                
        # Handle the last cluster
        if current_stay_points:
            first_point = current_stay_points[0]
            time_spent = current_stay_points[-1].timestamp_local - first_point.timestamp_local
            if time_spent >= timedelta(minutes=cls.STAY_DURATION_MINUTES):
                cls._create_stay_suggestion(trip, day_id, current_stay_points)
                suggestions_created += 1
                
        return suggestions_created

    @classmethod
    def _create_stay_suggestion(cls, trip, day_id, points):
        if not points: return
        first = points[0]
        last = points[-1]
        
        # We can calculate average location or just use the first point
        avg_lat = sum(float(p.lat) for p in points) / len(points)
        avg_lon = sum(float(p.lon) for p in points) / len(points)
        
        duration_mins = int((last.timestamp_local - first.timestamp_local).total_seconds() / 60)
        
        # We could use Reverse Geocoding here to get a title, but for now we keep it generic
        # or use geo_service if we have it
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
