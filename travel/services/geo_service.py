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
        
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        'q': location_name,
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
            print(f"Geocoding server returned error {response.status_code} for {location_name}")
            return None, None
            
        data = response.json()
        if data:
            return float(data[0]['lat']), float(data[0]['lon'])
    except Exception as e:
        print(f"Geocoding error for {location_name}: {e}")
        # Log response content if JSON decoding failed
        if 'response' in locals() and hasattr(response, 'text'):
            print(f"Response content: {response.text[:200]}")
        
    return None, None

def update_trip_coordinates(trip, limit=2):
    """
    Updates missing coordinates for all days in a trip.
    Returns True if more searchable days still need geocoding.
    """
    # A day is searchable if it has a location and isn't a placeholder
    searchable_missing = trip.days.filter(
        is_geocoded=False
    ).exclude(
        location=''
    ).exclude(
        location='Planung läuft...'
    )
    
    days_to_geocode = searchable_missing[:limit]
    
    for day in days_to_geocode:
        lat, lon = geocode_location(day.location)
        if lat and lon:
            day.latitude = lat
            day.longitude = lon
        day.is_geocoded = True
        day.save()
        time.sleep(1.5) # Be extra safe with Nominatim
            
    return trip.days.filter(is_geocoded=False).exclude(location='').exclude(location='Planung läuft...').exists()

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
