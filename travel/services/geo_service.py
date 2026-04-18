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
    
    # Smart extract: if string is "Frankfurt -> Prag" or "Frankfurt - Prag", take the first part
    clean_location = location_name
    if '->' in clean_location:
         clean_location = clean_location.split('->')[0].strip()
    elif ' - ' in clean_location:
         clean_location = clean_location.split(' - ')[0].strip()
         
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
            print(f"Geocoding server returned error {response.status_code} for {clean_location}")
            return None, None
            
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
    Returns True if more searchable items still need geocoding.
    """
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
        lat, lon = geocode_location(day.location)
        if lat and lon:
            day.latitude = lat
            day.longitude = lon
        day.is_geocoded = True
        day.save()
        time.sleep(1.5)
            
    # 2. Update Events (Travel types like FLIGHT, TRAIN, etc.)
    # Only if we still have room in our batch limit
    remaining_limit = limit - len(days_to_geocode)
    if remaining_limit > 0:
        from ..models import Event
        searchable_missing_events = Event.objects.filter(
            day__trip=trip,
            is_geocoded=False
        ).exclude(location='')
        
        events_to_geocode = searchable_missing_events[:remaining_limit]
        for event in events_to_geocode:
            lat, lon = geocode_location(event.location)
            if lat and lon:
                event.latitude = lat
                event.longitude = lon
            event.is_geocoded = True
            event.save()
            time.sleep(1.5)

    # Re-check if anything (Day or Event) is still pending
    days_pending = trip.days.filter(is_geocoded=False).exclude(location='').exclude(location='Planung läuft...').exists()
    from ..models import Event
    events_pending = Event.objects.filter(day__trip=trip, is_geocoded=False).exclude(location='').exists()
    
    return days_pending or events_pending

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
