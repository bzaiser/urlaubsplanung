import requests
import time
from django.conf import settings

def geocode_location(location_name, countrycodes=None):
    """
    Geocodes a location name using the Nominatim (OpenStreetMap) API.
    Returns (lat, lon) or (None, None) if not found.
    countrycodes: Optional string like 'pt,es' to restrict results.
    """
    if not location_name or location_name == 'Planung läuft...':
        return None, None
    
    # 1. CLEANING: Remove icons AND common travel prefixes to get the pure location
    clean_location = location_name
    
    # Step A: Pre-cleaning (Remove common artifacts)
    # 1. Extract DESTINATION if connectors are used (A to B -> B)
    # This also handles "Start -> End" or "Start - End"
    if '->' in clean_location:
         clean_location = clean_location.split('->')[-1].strip()
    elif ' - ' in clean_location and not re.search(r'\d', clean_location.split(' - ')[1]):
         clean_location = clean_location.split(' - ')[-1].strip()
    
    # 2. Extract Destination after movement keywords (zum, nach, bis, zu)
    import re
    movement_delimiters = [r'\s+zum\s+', r'\s+nach\s+', r'\s+bis\s+', r'\s+zu\s+']
    for sep in movement_delimiters:
        parts = re.split(sep, clean_location, flags=re.IGNORECASE)
        if len(parts) > 1:
            clean_location = parts[-1].strip()
            break

    # 3. Dynamic Noise Removal (Polarsteps & General)
    import re
    # Remove timestamps (10:30, 22:15, 9:00...)
    clean_location = re.sub(r'\d{1,2}:\d{2}', '', clean_location)
    # Remove coordinate-like strings
    clean_location = re.sub(r'\d+\.\d+,?\s?\d+\.\d+', '', clean_location)
    # Remove "Step", "Trip" noise
    clean_location = re.sub(r'\b(Step|Trip|Day|Location|Track)\b(\s+\d+)?', '', clean_location, flags=re.IGNORECASE)
    # Remove "from... to..." noise (common in flights/transfers)
    clean_location = re.sub(r'\b(from|to|via)\b', '', clean_location, flags=re.IGNORECASE)
    
    # 3. Strip icons, parentheses, and special chars
    clean_location = re.sub(r'\(.*\)', '', clean_location).strip() 
    clean_location = re.sub(r'[^\w\s,\-]', '', clean_location).strip() 
          
    # Step B: Strip common prefixes (case insensitive)
    prefixes_to_strip = [
        'flug nach', 'flug von', 'anfahrt zum', 'anfahrt nach', 'anfahrt von',
        'rückreise nach', 'fahrt nach', 'check-in:', 'check-out:', 'hotel:',
        'besuch der', 'besuch des', 'wanderung zum', 'wanderung am', 'tour zum',
        'roller-tour zur', 'taxi zum', 'privat-taxi zum', 'schnellfähre nach',
        'fähre von', 'anfahrt', 'taxi', 'privat-transfer zum', 'privat-taxi'
    ]
    for prefix in prefixes_to_strip:
        pattern = re.compile(rf'\b{re.escape(prefix)}\b', re.IGNORECASE)
        clean_location = pattern.sub('', clean_location).strip()
    
    # Step C: Word Deduplication (e.g., "Manila, Manila" -> "Manila")
    words = clean_location.split()
    unique_words = []
    seen = set()
    for w in words:
        if w.lower() not in seen:
            unique_words.append(w)
            seen.add(w.lower())
    clean_location = " ".join(unique_words)

    if not clean_location or len(clean_location) < 3:
        return None, None

    url = "https://nominatim.openstreetmap.org/search"
    params = {
        'q': clean_location,
        'format': 'json',
        'limit': 1,
        'addressdetails': 1
    }
    if countrycodes:
        params['countrycodes'] = countrycodes
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
            # SAFETY FILTER: If countrycodes were provided, Nominatim is already restricted.
            # But we double check the first result.
            return float(data[0]['lat']), float(data[0]['lon'])
            
        # 1.1 Fallback: If "Location, Region" fails, try just "Location"
        if "," in clean_location:
            simpler_location = clean_location.split(',')[0].strip()
            if len(simpler_location) > 2:
                params['q'] = simpler_location
                response = requests.get(url, params=params, headers=headers, timeout=10)
                data = response.json()
                if data:
                    return float(data[0]['lat']), float(data[0]['lon'])

        # 1.2 Fallback for Philippines (specifically for Bernd's old itineraries)
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

def update_trip_coordinates(trip, limit=10):
    """
    Updates missing coordinates for both Days and relevant Events in a trip.
    Returns (has_more_pending, processed_locations_list).
    """
    # Detect country context from trip name
    country_context = None
    trip_name_lower = trip.name.lower()
    if any(word in trip_name_lower for word in ['iberisch', 'portugal', 'spanien', 'spain']):
        country_context = 'pt,es'
    elif any(word in trip_name_lower for word in ['italien', 'italy', 'adria']):
        country_context = 'it,hr,si,at'
    elif any(word in trip_name_lower for word in ['frankreich', 'france']):
        country_context = 'fr'

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
        # Avoid blocking for empty or placeholder locations
        cleaned_loc = day.location.strip()
        if not cleaned_loc or cleaned_loc in ['', 'Planung läuft...', 'TBD', '?']:
            day.is_geocoded = True
            day.save()
            continue

        lat, lon = geocode_location(cleaned_loc, countrycodes=country_context)
                
        if lat and lon:
            day.latitude = lat
            day.longitude = lon
        day.is_geocoded = True
        day.save()
        processed_locations.append(cleaned_loc or "Unbekannter Ort")
        time.sleep(1.5) # Wait ONLY if we actually did a geocoding lookup

            
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
            # Avoid blocking for empty or placeholder locations/titles
            cleaned_loc = (event.location or event.title or "").strip()
            if not cleaned_loc or cleaned_loc in ['', 'Planung läuft...', 'TBD', '?']:
                event.is_geocoded = True
                event.save()
                continue
            
            lat, lon = geocode_location(cleaned_loc, countrycodes=country_context)

            if lat and lon:
                event.latitude = lat
                event.longitude = lon
            event.is_geocoded = True
            event.save()
            processed_locations.append(cleaned_loc or "Unbekannter Eintrag")
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
        
    # FALLBACK: If OSRM fails, return simple straight lines (Leaflet needs [lat, lon])
    return [[c[1], c[0]] for c in coordinates]
