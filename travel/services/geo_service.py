import requests
import time
from django.conf import settings

def geocode_location(location_name):
    """
    Geocodes a location name using the Nominatim (OpenStreetMap) API.
    Returns (lat, lon) or (None, None) if not found.
    """
    if not location_name or location_name == 'Planung läuft...':
        return None, None
    
    # 1. CLEANING: Remove common travel prefixes to get the pure location
    clean_location = location_name
    
    # Extract first part if "Start -> End"
    if '->' in clean_location:
         clean_location = clean_location.split('->')[0].strip()
    elif ' - ' in clean_location:
         clean_location = clean_location.split(' - ')[0].strip()
         
    # Strip common prefixes (case insensitive)
    prefixes_to_strip = [
        'flug nach', 'flug von', 'anfahrt zum', 'anfahrt nach', 'anfahrt von',
        'rückreise nach', 'fahrt nach', 'check-in:', 'check-out:', 'hotel:',
        'besuch der', 'besuch des', 'wanderung zum', 'wanderung am', 'tour zum',
        'roller-tour zur', 'taxi zum', 'privat-taxi zum', 'schnellfähre nach',
        'fähre von', 'flug nach'
    ]
    import re
    for prefix in prefixes_to_strip:
        pattern = re.compile(re.escape(prefix), re.IGNORECASE)
        clean_location = pattern.sub('', clean_location).strip()
    
    # Final cleanup (strip icons and special chars)
    clean_location = re.sub(r'[^\w\s,\-]', '', clean_location).strip()

    if not clean_location or len(clean_location) < 3:
        return None, None

    url = "https://nominatim.openstreetmap.org/search"
    params = {
        'q': clean_location,
        'format': 'json',
        'limit': 1,
        'addressdetails': 1
    }
    # Use a unique User-Agent as required by Nominatim's Usage Policy
    headers = {
        'User-Agent': 'ZaiserUrlaubsplaner/1.5 (https://zaisers.myds.me/; admin@zaiser.de)',
        'Accept-Language': 'de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7'
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        if response.status_code != 200:
            return None, None
            
        data = response.json()
        if data:
            return float(data[0]['lat']), float(data[0]['lon'])
            
        # 1.1 Fallback for Philippines (specifically for Bernd's current itinerary)
        if "," not in clean_location:
            params['q'] = f"{clean_location}, Philippines"
            response = requests.get(url, params=params, headers=headers, timeout=10)
            data = response.json()
            if data:
                return float(data[0]['lat']), float(data[0]['lon'])
                
    except Exception as e:
        print(f"Geocoding error for {clean_location}: {e}")
        # Log response content if JSON decoding failed
        if 'response' in locals() and hasattr(response, 'text'):
            print(f"Response content: {response.text[:200]}")
        
    return None, None

def update_trip_coordinates(trip, limit=2):
    """
    Updates missing coordinates for both Days and relevant Events in a trip.
    Returns (has_more_pending, processed_locations_list).
    """
    processed_locations = []
    
    # 1. Update Days first (highest priority for map)
    searchable_missing_days = trip.days.filter(
        is_geocoded=False
    ).exclude(
        location=''
    ).exclude(
        location='Planung läuft...'
    )
    
    days_to_geocode = searchable_missing_days[:limit]
    for day in days_to_geocode:
        # Try Location
        candidate_strings = [day.location]
        lat, lon = None, None
        best_name = day.location
        for s in candidate_strings:
            if s and len(s) > 2:
                lat, lon = geocode_location(s)
                if lat and lon: 
                    best_name = s
                    break
                
        if lat and lon:
            day.latitude = lat
            day.longitude = lon
        day.is_geocoded = True
        day.save()
        processed_locations.append(best_name or "Unbekannter Ort")
        time.sleep(1.5)
            
    # 2. Update Events (Only travel types that affect the route)
    remaining_limit = limit - len(days_to_geocode)
    if remaining_limit > 0:
        from ..models import Event
        searchable_missing_events = Event.objects.filter(
            day__trip=trip,
            is_geocoded=False,
            type__in=['FLIGHT', 'TRAIN', 'FERRY', 'BUS', 'CAR']
        )
        
        events_to_geocode = searchable_missing_events[:remaining_limit]
        for event in events_to_geocode:
            # Try Location, then Title, then Info
            candidate_strings = [event.location, event.title, event.info]
            lat, lon = None, None
            best_name = event.location or event.title
            for s in candidate_strings:
                if s and len(s) > 2:
                    lat, lon = geocode_location(s)
                    if lat and lon: 
                        best_name = s
                        break

            if lat and lon:
                event.latitude = lat
                event.longitude = lon
            event.is_geocoded = True
            event.save()
            processed_locations.append(best_name or "Unbekannter Eintrag")
            time.sleep(1.5)

    # Re-check if anything (Day or Event) is still pending
    days_pending = trip.days.filter(is_geocoded=False).exclude(location='').exclude(location='Planung läuft...').exists()
    from ..models import Event
    events_pending = Event.objects.filter(day__trip=trip, is_geocoded=False, type__in=['FLIGHT', 'TRAIN', 'FERRY', 'BUS', 'CAR']).exclude(location='').exists()
    
    return (days_pending or events_pending), processed_locations

def get_route_geometry(coordinates):
    """
    Fetches real road routing geometry from OSRM.
    coordinates: List of [lon, lat] pairs
    Returns: List of [lat, lon] pairs for the road route
    """
    if len(coordinates) < 2:
        return []
        
    # OSRM expects lon,lat;lon,lat
    coords_str = ";".join([f"{c[0]},{c[1]}" for c in coordinates])
    url = f"http://router.project-osrm.org/route/v1/driving/{coords_str}"
    params = {
        'overview': 'full',
        'geometries': 'geojson'
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        if data.get('routes'):
            # GeoJSON gives [lon, lat], Leaflet needs [lat, lon]
            geometry = data['routes'][0]['geometry']['coordinates']
            return [[p[1], p[0]] for p in geometry]
    except Exception as e:
        print(f"Routing error: {e}")
        
    return []
