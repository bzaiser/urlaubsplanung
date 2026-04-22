import json
import requests
import time
import logging
import re
import os
from json_repair import repair_json as pro_repair
from ..models import GlobalSetting

logger = logging.getLogger(__name__)
from . import logic_service

def get_setting(key, default='', user=None):
    """Helper to fetch settings from the GlobalSetting model, filtered by user."""
    try:
        return GlobalSetting.objects.get(key=key, user=user).value
    except:
        # Fallback for old calls without user context - try to find admin default
        try:
            if not user:
                return GlobalSetting.objects.filter(key=key, user__isnull=True).first().value
            return default
        except:
            return default

def safe_float(val, default=0.0):
    """Safely converts a value to float, handling None, empty strings, and malformed text."""
    if val is None or val == "":
        return default
    try:
        if isinstance(val, str):
            # Handle German decimal comma
            val = val.replace(',', '.')
            # Remove any non-numeric characters except . and -
            val = "".join(c for c in val if c.isdigit() or c in '.-')
            if not val or val == '.' or val == '-':
                return default
        return float(val)
    except (ValueError, TypeError):
        return default

def safe_int(val, default=0):
    """Safely converts a value to int."""
    if val is None or val == "":
        return default
    try:
        if isinstance(val, str):
            val = "".join(c for c in val if c.isdigit() or c == '-')
            if not val or val == '-':
                return default
        return int(float(val)) # float middle-man handles "14.0" strings
    except (ValueError, TypeError):
        return default

def strip_duration_from_name(name):
    """
    Removes redundant duration info in brackets from the name.
    Example: 'Thailand (14 Nächte)' -> 'Thailand'
    Matches patterns like (14 Nächte), [5 Tage], (10 nights), etc.
    """
    if not name:
        return name
    # Regex for stripping brackets containing days/nights/tage/nächte etc.
    # It looks for anything in () or [] that contains one of the keywords.
    pattern = r'\s*[\(\[].*?(?:Nächte|Nächten|Tage|Tagen|Nights|Days|Night|Day).*?[\)\]]'
    cleaned = re.sub(pattern, '', name, flags=re.IGNORECASE).strip()
    return cleaned

def repair_json(json_str):
    """
    Highly robust JSON repair using the "json-repair" library.
    Handles German decimal commas and LLM truncation/mess.
    """
    if not json_str:
        return "{}"
    
    # 1. Isolate the JSON object (strip preamble and postamble)
    start_idx = json_str.find("{")
    end_idx = max(json_str.rfind("}"), json_str.rfind("]"))
    
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        json_str = json_str[start_idx:end_idx+1]

    # 2. Fix German decimal commas (e.g., 20,50 -> 20.50)
    import re
    json_str = re.sub(r"(\d),(\d)", r"\1.\2", json_str)
    
    # 3. Use professional json-repair library
    try:
        from json_repair import repair_json as pro_repair
        repaired = pro_repair(json_str)
        # Verify it is actually valid
        import json
        json.loads(repaired)
        return repaired
    except Exception as e:
        logger.error(f"Professional repair failed context: {json_str[:200]}...")
        return json_str

def get_itinerary_prompt(preferences, start_date, days, start_location, persons_count, persons_ages, user=None):
    """Returns the raw prompt text for manual copy-pasting into external LLMs."""
    v1_name = get_setting('vehicle1_name', 'Camper', user=user)
    v1_range = get_setting('vehicle1_range', '400', user=user)
    v2_name = get_setting('vehicle2_name', 'PKW', user=user)
    
    system_text = (
        "Du bist ein Weltklasse-Reiseplaner. Erstelle einen detaillierten Reiseplan auf DEUTSCH.\n"
        "REIHENFOLGE DER ANTWORT:\n"
        "1. BEGRÜNDUNG: Erkläre kurz deine Wahl der Route und Transportmittel.\n"
        "2. KLARTEXT-VORSCHAU: Zeige den Plan in lesbarer Textform an.\n"
        "3. JSON-DATEN: Gib am Ende den Plan als valides JSON-Objekt aus.\n\n"
        "REGELN:\n"
        "1. SPRACHE: Alles auf DEUTSCH.\n"
        "2. KONKRET: Nenne EXAKTE Namen von Sehenswürdigkeiten, Hotels und Flughäfen im Feld 'location'. Vermeide pauschale Städtenamen (wie nur 'Manila'), wenn ein genauer POI (z.B. 'City Garden Grand Hotel') bekannt ist. Keine Platzhalter!\n"
        "3. DAUER & TERMINE: Erzeuge EXAKT " + str(days) + " Tage. " + ("Halte dich STRIKT an das Startdatum (" + str(start_date) + ")." if int(days) < 7 else "Das Startdatum ist " + str(start_date) + ".") + "\n"
    )
    
    if int(days) >= 7:
        system_text += "4. FLEXIBILITÄT: Du darfst das Startdatum um +-4 Tage und die Dauer um +-3 Tage variieren, um bessere Flüge/Preise zu finden.\n"
    
    system_text += (
        "5. SICHERHEIT: Bei Flügen KEINE Zwischenlandungen in Krisengebieten!\n"
        "6. LOGISTIK: Berücksichtige den Startort " + start_location + ". Plane zwingend sowohl den Weg zum Startflughafen (Hinfahrt) als auch den Weg vom Zielflughafen/Parkplatz zurück nach Hause (Rückfahrt) als eigene Events ein.\n"
        "7. FAHRZEUGE: Nutze ein " + v1_name + " (Reichweite " + v1_range + "km) NUR, wenn die Reise explizit als Wohnmobil-Tour bezeichnet wird oder das Ziel dafür bekannt ist (z.B. Neuseeland, Island, Roadtrip). In allen anderen Fällen (wie Strand-Bungalow-Urlaub) nutze " + v2_name + ", Roller (SCOOTER), TAXI oder Fähre für Teilstrecken.\n"
        "8. STIL: Bevorzuge Bungalows in Strandnähe, lokale Streetfood-Märkte (RESTAURANT) und Aktivitäten wie Wandern, Tauchen oder Roller-Touren.\n"
        "9. SICHERHEIT: KEINE Bilder, KEINE Google Maps Links, KEINE externen Medien in der Antwort.\n"
        "10. LOGISTIK: Jeder einzelne der " + str(days) + " Tage MUSS mindestens ein Event enthalten (KEINE leeren Tage).\n"
        "11. LOGISTIK: Nutze für JEDES Event einen präzisen, geokodierbaren Standort (z.B. 'Flughafen Frankfurt', 'Hotel Adlon Berlin'). Ermittle für JEDEN Ort und JEDES Event zusätzlich die exakten Koordinaten (Breiten- und Längengrad), damit wir die Route schön auf einer Karte anzeigen können. Gib diese als 'lat' and 'lon' (Float-Zahlen) im JSON aus.\n"
        "12. LOGISTIK: Bei JEDEM Transport-Event MUSS ein Feld 'distance_km' (als Zahl) und 'end_time' (Ankunftszeit als HH:MM) vorhanden sein.\n"
        "13. LOGISTIK: Bei JEDER Aktivität MUSS ein Feld 'end_time' (Ende der Aktivität) vorhanden sein.\n"
        "14. LOGISTIK: Bei Langstrecken mit Zwischenlandungen MUSS für JEDES einzelne Flugsegment (Leg) ein eigenes Event erstellt werden (z.B. Event 1: Manila -> Doha, Event 2: Doha -> Frankfurt). Jedes Segment benötigt eigene Zeiten und Koordinaten für die Karte.\n"
        "15. LOGISTIK: Das Feld 'location' MUSS immer das KONKRETE ZIEL des jeweiligen Segments enthalten (z.B. 'Flughafen Frankfurt'). Die vollständige Reisekette darf NUR in den Notizen stehen.\n"
        "16. HIERARCHIE: Gruppiere die Reise in 'stations' (Stopps/Aufenthalte). Eine Station entspricht EXAKT einem Übernachtungsort (z.B. ein spezifischer Campingplatz, Stellplatz oder ein Hotel) und umfasst alle Tage, die man dort als Basis verbringt. Gruppiere NICHT nach ganzen Ländern oder Inseln! WICHTIG: Gib ZUSÄTZLICH für JEDEN Tag ein Feld 'location' an, das den spezifischen Ort dieses Tages beschreibt (z.B. das Ziel eines Ausflugs).\n"
        "17. UNTERKÜNFTE: Gruppiere ALLE festen Unterkünfte (Hotel, Bungalow, Airbnb, Ferienhaus) als 'HOTEL'. Nutze 'CAMPING' (Campingplatz) oder 'PITCH' (Stellplatz/Freies Stehen) NUR bei Wohnmobil-Touren.\n"
        "18. VERPFLEGUNG: Wenn Verpflegungswünsche (Selbstkochen vs. Restaurant) vorhanden sind, berechne KEINE Euro-Beträge. Gib stattdessen ein Objekt 'food_preferences' mit den Feldern 'cooking_ratio' (0.0-1.0), 'dining_out_ratio' (0.0-1.0) und 'price_level' ('low', 'med', 'high') aus.\n"
        "19. GLOBAL_EXPENSES: Erfasse NUR zusätzliche Gebühren wie 'Maut', 'Vignette' oder 'Fähre-Pauschale' in der Liste 'global_expenses'. (KEINE Verpflegung hier eintragen!).\n"
        "20. REISEGRUPPE: Berücksichtige bei der Planung (Zimmerwahl, Restaurants, Aktivitäten) die Anzahl und das Alter der Personen.\n"
        "21. UNTERKUNFT-DAUER: Gib bei JEDEM Check-in (HOTEL, CAMPING, PITCH) das Feld 'nights' (Anzahl der Nächte) an. Die Summe der Nächte muss die gesamte Reisedauer abdecken.\n"
        "22. TRANSPORT-TYPEN: Nutze für die Klassifizierung (Feld 'type') folgende Tabelle für lokale Begriffe:\n"
        "Land | ZUG (TRAIN) | METRO (METRO) | STRASSENBAHN (TRAM)\n"
        "DE | Zug, Bahn | U-Bahn | Straßenbahn, Tram\n"
        "FR/BE | Train | Métro | Tramway\n"
        "IT | Treno | Metropolitana | Tram\n"
        "ES/PT | Tren/Comboio | Metro | Tranvía/Eléctrico\n"
        "UK | Train | Underground/Tube | Tram\n\n"
        "19. FORMAT (AM ENDE DER ANTWORT ALS JSON):\n"
        "{\n"
        "  \"name\": \"Reise-Titel\",\n"
        "  \"assistant_reasoning\": \"...\",\n"
        "  \"stations\": [\n"
        "    {\n"
        "       \"name\": \"Station: El Nido (Camping XYZ)\",\n"
        "       \"location\": \"El Nido\",\n"
        "       \"lat\": 1.23, \"lon\": 45.67,\n"
        "       \"days\": [\n"
        "         {\n"
        "            \"day_number\": 1,\n"
        "            \"location\": \"Spezifischer Tagesort (z.B. El Nido)\",\n"
        "            \"events\": [\n"
        "              {\"title\": \"Check-in: Hotel Name\", \"type\": \"HOTEL\", \"nights\": 2, \"lat\": 1.23, \"lon\": 45.67, \"time\": \"14:00\", \"end_time\": \"15:00\"}\n"
        "            ]\n"
        "         }\n"
        "       ]\n"
        "    }\n"
        "  ],\n"
        "  \"food_preferences\": {\"cooking_ratio\": 0.5, \"dining_out_ratio\": 0.5, \"price_level\": \"med\"},\n"
        "  \"global_expenses\": [{\"title\": \"Maut\", \"type\": \"FEE\", \"cost\": 15}]\n"
        "}\n"
    )
    user_text = f"Sonderwünsche/Ziel: {preferences}. Starttermin: {start_date}. Dauer: {days} Tage. Personen: {persons_count} (Alter: {persons_ages})."
    
    return f"{system_text}\n\n{user_text}"

def normalize_itinerary(data):
    """
    Ensures the itinerary has a standard structure and maps common 
    synonyms for keys used by different AI providers.
    """
    # 0. Handle direct lists (if AI skipped the wrapping object)
    if isinstance(data, list):
        data = {"days": data}
        
    if not isinstance(data, dict):
        return {"error": f"KI lieferte Text statt Daten: {str(data)[:100]}..."}

    # 0. Prevent collision if 'days' is just a number (AI sometimes does this)
    if 'days' in data and not isinstance(data['days'], (list, dict)):
        data['days_count_raw'] = data['days']
        del data['days']
        
    # 1. Handle wrapping
    for key in ['itinerary', 'trip', 'travel_plan']:
        if key in data and isinstance(data[key], dict):
            # Preserve existing top-level fields (like food_preferences) 
            # while unwrapping the main container
            nested = data.pop(key)
            for k, v in nested.items():
                if k not in data:
                    data[k] = v
            break
            
    # 2. Map synonyms
    mapping = {
        'itinerary': 'days',
        'travel_plan': 'days',
        'plan': 'days',
        'itinerary_days': 'days',
        'route': 'days',
        'reasoning': 'assistant_reasoning',
        'thoughts': 'assistant_reasoning',
        'explanation': 'assistant_reasoning',
        'details': 'assistant_reasoning'
    }
    for old_key, new_key in mapping.items():
        if old_key in data and new_key not in data:
            data[new_key] = data[old_key]

    # 2.5 Handle NEW 'stations' hierarchy (Station -> Day -> Event)
    if 'stations' in data and isinstance(data['stations'], list) and 'days' not in data:
        flattened_days = []
        for station in data['stations']:
            station_name = station.get('name', station.get('location', 'Station'))
            station_loc = station.get('location', station_name)
            station_lat = station.get('lat')
            station_lon = station.get('lon')
            
            for day in station.get('days', []):
                if isinstance(day, dict):
                    # Set the new DB field 'station'
                    day['station'] = station_name
                    # Also ensure day has the station's location/coordinates if missing
                    if 'location' not in day or not day['location']:
                        day['location'] = station_loc
                    if 'lat' not in day: day['lat'] = station_lat
                    if 'lon' not in day: day['lon'] = station_lon
                    flattened_days.append(day)
        data['days'] = flattened_days
            
    # 3. Ensure 'days' is present (and check nested keys again)
    if 'days' not in data:
        # Look for anything that might be the list/dict of days
        for k, v in data.items():
            if isinstance(v, (list, dict)) and len(v) > 0:
                # If it's a dict where keys are "1", "2" or "Day 1", "Day 2"
                if isinstance(v, dict):
                    # Convert dict to list
                    data['days'] = list(v.values())
                    break
                elif isinstance(v, list) and (isinstance(v[0], dict) or isinstance(v[0], str)):
                    data['days'] = v
                    break
                    
    # 4. Final Fallback: If 'days' is still nothing but data has 'events'
    if 'days' not in data and 'events' in data and isinstance(data['events'], list):
        data['days'] = [{"location": "Reiseplan", "events": data['events']}]
        
    # 5. Handle top-level list correctly if it survived this far
    if 'days' not in data:
         # Check if there is ANY list in the values
         for v in data.values():
             if isinstance(v, list) and len(v) > 0:
                 data['days'] = v
                 break

    # 6. Normalize Days and Events
    if 'days' in data and isinstance(data['days'], list):
        last_location = "Unbekannt"
        for i, day in enumerate(data['days']):
            # Ensure day is a dictionary (AI sometimes sends strings or ints)
            if not isinstance(day, dict):
                day = {"location": str(day), "events": []}
                data['days'][i] = day
                
            # Ensure 'offset' (Order matters!)
            if 'offset' not in day or day.get('offset') is None:
                day['offset'] = i
                
            # Ensure 'location'
            if 'location' not in day or not day.get('location'):
                # Try to find location in other fields, or fallback to last_location
                day['location'] = day.get('city', day.get('destination', day.get('place', day.get('ort', day.get('stadt', day.get('stopover', last_location))))))
            
            last_location = day['location']
            
            if 'events' in day and isinstance(day['events'], list):
                for j, event in enumerate(day['events']):
                    # Ensure event is a dict, not a string
                    if isinstance(event, str):
                        event = {"title": event, "type": "OTHER", "cost_estimated": 0}
                        day['events'][j] = event
                        
                    # Map synonyms for 'title'
                    if 'title' not in event or not event['title']:
                        event['title'] = event.get('name', event.get('activity', event.get('description', 'Aktivität')))
                    
                    # Map synonyms for 'location' (Event level)
                    if 'location' not in event or not event['location'] or event['location'] == day['location']:
                        # Try to extract from title if it's a transport event and location is just the day's start
                        potential_loc = event.get('city', event.get('place', event.get('destination', event.get('ort'))))
                        if not potential_loc and (event.get('type') in ['FLIGHT', 'TRAIN', 'BUS', 'CAR', 'FERRY']):
                            # Simple extraction: "Flight to Manila" -> "Manila"
                            title = event.get('title', '')
                            if ' nach ' in title:
                                potential_loc = title.split(' nach ')[-1].strip()
                            elif ' to ' in title.lower():
                                potential_loc = title.lower().split(' to ')[-1].strip().title()
                            elif ':' in title:
                                potential_loc = title.split(':')[-1].strip()
                        
                        event['location'] = potential_loc or event.get('location', day['location'])

                    # Map synonyms for 'cost_estimated'
                    if 'cost_estimated' not in event or not event['cost_estimated']:
                        # Try direct keys
                        cost_val = event.get('cost', event.get('price', event.get('eur', event.get('price_per_night', event.get('rate', 0)))))
                        
                        # New: Robust extraction from text (description/notes) if cost is missing
                        if not cost_val:
                            text_to_search = str(event.get('description', '')) + " " + str(event.get('notes', ''))
                            # Search for patterns like "85 EUR", "85€", "Preis: 85", "Cost: 85"
                            # We use a non-greedy search for the first number followed by currency or preceded by price keyword
                            import re
                            # Pattern: Look for "Preis/Cost/Price: XX" or "XX EUR/€"
                            patterns = [
                                r'(?:Preis|Cost|Price|rate|EUR|per night)[:\s]*([\d.,]+)',
                                r'([\d.,]+)\s*(?:EUR|€|Euro)'
                            ]
                            for pattern in patterns:
                                match = re.search(pattern, text_to_search, re.IGNORECASE)
                                if match:
                                    try:
                                        raw_val = match.group(1).replace(',', '.')
                                        cost_val = safe_float(raw_val)
                                        break
                                    except: continue
                        
                        event['cost_estimated'] = cost_val

                    # Map synonyms for 'notes'
                    if 'notes' not in event or not event['notes']:
                        event['notes'] = event.get('description', event.get('info', event.get('details', '')))

                    # Map synonyms for 'booking_url'
                    if 'booking_url' not in event or not event['booking_url']:
                        event['booking_url'] = event.get('url', event.get('link', event.get('booking_link', '')))

                    # Map synonyms for 'end_time' and 'time'
                    if 'time' not in event or not event['time']:
                        event['time'] = event.get('start_time', event.get('beginn', event.get('start', event.get('von', ''))))
                    if 'end_time' not in event or not event['end_time']:
                        event['end_time'] = event.get('arrival', event.get('ankunft', event.get('ende', event.get('end', event.get('bis', '')))))

                    # Map synonyms for 'distance_km'
                    if 'distance_km' not in event:
                        dist_val = event.get('km', event.get('distanz', event.get('distance', event.get('entfernung', event.get('strecke', 0)))))
                        event['distance_km'] = dist_val

                    # Map synonyms for 'nights'
                    if 'nights' not in event:
                        event['nights'] = event.get('naechte', event.get('nächte', event.get('duration_nights', None)))

                    # 4. Map Event Types for Icons
                    etype_raw = str(event.get('type' or 'OTHER')).upper()
                    type_map = {
                        'SIGHTSEEING': 'ACTIVITY', 'MUSEUM': 'ACTIVITY', 'CULTURE': 'ACTIVITY', 'WALK': 'ACTIVITY', 'TOUR': 'ACTIVITY',
                        'FOOD': 'RESTAURANT', 'MEAL': 'RESTAURANT', 'DINNER': 'RESTAURANT', 'LUNCH': 'RESTAURANT', 'BREAKFAST': 'RESTAURANT',
                        'STAY': 'HOTEL', 'SLEEP': 'HOTEL', 'ACCOMMODATION': 'HOTEL', 'AIRBNB': 'HOTEL', 'FERIENHAUS': 'HOTEL', 'BUNGALOW': 'HOTEL',
                        'CAMPINGPLATZ': 'CAMPING', 'STELLPLATZ': 'PITCH', 'SOSTA': 'PITCH', 'AREA SOSTA': 'PITCH', 'CAMPER STOP': 'PITCH',
                        'CAMPING SITE': 'CAMPING', 'HOLIDAY PARK': 'CAMPING', 'DRIVE': 'CAR', 'DRIVING': 'CAR', 'TRAVEL': 'CAR', 'TRANSPORT': 'OTHER', 'PKW': 'CAR'
                    }
                    
                    # Apply specific mapping
                    if etype_raw in type_map:
                        event['type'] = type_map[etype_raw]
                    else:
                        # Only use the raw type if it's already one of our known base types
                        allowed = ['FLIGHT', 'HOTEL', 'CAMPING', 'PITCH', 'CAMPER', 'CAR', 'SCOOTER', 'BOAT', 'FERRY', 'TAXI', 'BUS', 'TRAIN', 'METRO', 'TRAM', 'ACTIVITY', 'RESTAURANT', 'OTHER', 'FOOD', 'FEE', 'RENTAL', 'RENTAL_CAR', 'BUNGALOW']
                        if etype_raw not in allowed:
                            event['type'] = 'OTHER'
                        else:
                            event['type'] = etype_raw

                    # New: Smart Keywords Check for Transport differentiation (International)
                    if event['type'] in ['CAR', 'OTHER', 'TRANSPORT', 'TRAIN', 'METRO', 'TRAM', 'BUS']:
                        suggested_type, _ = logic_service.resolve_event_type(
                            event.get('title', ''), 
                            event.get('notes', ''), 
                            event.get('description', '')
                        )
                        if suggested_type:
                            event['type'] = suggested_type
                        elif event['type'] == 'OTHER' and etype_raw == 'TRANSPORT':
                            event['type'] = 'CAR'

                    # 5. Smart Title & Nights for Stays (NEW)
                    stay_types = ['HOTEL', 'CAMPING', 'PITCH', 'BUNGALOW']
                    if event['type'] in stay_types:
                        curr_title = event.get('title', '')
                        curr_title_lower = curr_title.lower()
                        # If no check-in/out marker, assume check-in
                        if not any(k in curr_title_lower for k in ['check-in', 'check-out', 'ankunft', 'abreise', 'übernahme', 'rückgabe', 'abholung']):
                            event['title'] = f"Check-in: {curr_title}"
                        
                        # Ensure nights is at least 1 for check-ins to trigger auto-checkout
                        if 'check-in' in event['title'].lower() and (not event.get('nights') or event['nights'] == 0):
                            event['nights'] = 1

                        # Pitch / Area Sosta signals (International)
                        pitch_keywords = [
                            'sosta', 'stellplatz', 'wohnmobilstellplatz', 'weingutstellplatz', 'pitch', 'camper stop', 'aire de camping', 'aire municipale', 
                            'aire de service', 'area sosta', 'agricampeggio', 'area attrezzata', 'área autocaravanas', 'parque autocaravanas', 'asa', 'camperplaats', 
                            'jachthaven', 'motorhomeplaats', 'autocamperplads', 'ställplats', 'gårdsställplatz', 'bobilplass', 'gårdscamping', 'matkailuauto paikka', 
                            'caravan-area', 'motorhome stopover', 'pub stopover', 'miejsce camperowe', 'karavanové stání', 'camper stop', 'mini-camp', 'χωρος αυτοκινουμενων',
                            'bodega camper', 'parking autocaravanas', 'stopover'
                        ]
                        # Camping signals
                        camping_keywords = [
                            'camping', 'campingplatz', 'holiday park', 'caravan park', 'camp area', 'minicamping', 'bondegård camping', 'agroturystyka', 'autocamp', 'agrotourism camping'
                        ]
                        
                        title_lower = event.get('title', '').lower()
                        if any(k in title_lower for k in pitch_keywords):
                            event['type'] = 'PITCH'
                        elif any(k in title_lower for k in camping_keywords):
                            event['type'] = 'CAMPING'

        # 5. Smart Promotion (Trip-wide context)
        # If the trip contains any CAMPER/CAMPING/PITCH signal, promote all generic drives to CAMPER
        is_camper_trip = False
        trip_title = str(data.get('name', '')).lower()
        if any(k in trip_title for k in ['wohnmobil', 'camper', 'womo', 'mobil']):
            is_camper_trip = True
        
        if not is_camper_trip:
            # Check if any event is already camper/camping related
            for day in data['days']:
                for event in day.get('events', []):
                    if event.get('type') in ['CAMPER', 'CAMPING', 'PITCH']:
                        is_camper_trip = True
                        break
                if is_camper_trip: break
        
        if is_camper_trip:
            for day in data['days']:
                for event in day.get('events', []):
                    if event.get('type') in ['CAR', 'TRANSPORT', 'OTHER']:
                        # If it's a driving/transport event in a camper trip, it's a CAMPER
                        transport_keywords = ['fahrt', 'drive', 'reise', 'überfahrt', 'route', 'etappe', 'strecke', 'grenz', 'uebergang', 'home', 'heimat', 'nach hause', 'transfer', 'transit']
                        if any(k in title_lower for k in transport_keywords):
                            event['type'] = 'CAMPER'
                        # Extra safety: if it was already marked as CAR or TRANSPORT by AI, but it's a camper trip
                        elif event.get('type') in ['CAR', 'TRANSPORT']:
                            event['type'] = 'CAMPER'
        
        # Normalize Global Expenses
        if 'global_expenses' in data and isinstance(data['global_expenses'], list):
            for k, gx in enumerate(data['global_expenses']):
                if isinstance(gx, str):
                    data['global_expenses'][k] = {"title": gx, "type": "FEE", "cost": 0}
                elif not isinstance(gx, dict):
                    data['global_expenses'][k] = {"title": str(gx), "type": "FEE", "cost": 0}
                    
    return data

def save_itinerary_to_db(trip_data, start_date, persons_count=2, persons_ages="", user=None):
    """
    Takes a JSON itinerary and creates Trip, Day, and Event objects.
    """
    from ..models import Trip, Day, Event
    from datetime import datetime, timedelta
    
    # Normalize data before saving
    trip_data = normalize_itinerary(trip_data)
    
    if not isinstance(trip_data, dict) or 'error' in trip_data:
        raise ValueError(trip_data.get('error') if isinstance(trip_data, dict) else "Ungültige Reisedaten")
    
    if not start_date:
        start_date = datetime.now().date()
    elif isinstance(start_date, str):
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()

    trip_name = strip_duration_from_name(trip_data.get('name', 'Neue KI Reise'))

    trip = Trip.objects.create(
        user=user,
        name=trip_name,
        start_date=start_date,
        persons_count=safe_int(persons_count, 2),
        persons_ages=persons_ages or ""
    )
    
    days_data = trip_data.get('days', [])
    for d_data in days_data:
        # Extra safety for malformed days
        if not isinstance(d_data, dict): continue
        offset = d_data.get('offset', 0)
        day_date = start_date + timedelta(days=offset)
        
        day = Day.objects.create(
            trip=trip,
            date=day_date,
            location=d_data.get('location', 'Unbekannt'),
            station=d_data.get('station', ''),
            latitude=safe_float(d_data.get('lat')) if d_data.get('lat') else None,
            longitude=safe_float(d_data.get('lon')) if d_data.get('lon') else None,
            is_geocoded=True if d_data.get('lat') and d_data.get('lon') else False
        )
        
        # Load settings for automated cost calculation
        v1_cons = safe_float(get_setting('vehicle1_consumption', '12', user=user))
        v2_cons = safe_float(get_setting('vehicle2_consumption', '8', user=user))
        diesel_p = safe_float(get_setting('diesel_price', '1.60', user=user))
        petrol_p = safe_float(get_setting('petrol_price', '1.70', user=user))
        
        for e_data in d_data.get('events', []):
            time_v = e_data.get('time')
            end_v = e_data.get('end_time')
            
            # Extract distance_km robustly
            dist_raw = e_data.get('distance_km', e_data.get('km', e_data.get('distance', 0)))
            dist_final = 0
            if dist_raw:
                try:
                    import re
                    nums = re.findall(r'\d+', str(dist_raw))
                    if nums: dist_final = int(nums[0])
                except: pass

            e_obj = Event(
                day=day,
                title=e_data.get('title', 'Event'),
                type=e_data.get('type', 'OTHER'),
                location=str(e_data.get('location', '')).strip(),
                cost_estimated=safe_float(e_data.get('cost_estimated', 0)),
                distance_km=dist_final,
                nights=safe_int(e_data.get('nights')),
                notes=e_data.get('notes', ''),
                booking_url=e_data.get('booking_url', ''),
                booking_reference=e_data.get('booking_reference', ''),
                detail_info=e_data.get('detail_info', e_data.get('flight_number', '')),
                latitude=safe_float(e_data.get('lat')) if e_data.get('lat') else None,
                longitude=safe_float(e_data.get('lon')) if e_data.get('lon') else None,
                is_geocoded=True if e_data.get('lat') and e_data.get('lon') else False
            )
            e_obj._skip_automation = True # [FAST LANE] bypass slow side effects
            
            def clean_time(t):
                if not t: return None
                t = str(t).strip().lower()
                if 'uhr' in t: t = t.replace('uhr', '').strip()
                if len(t) == 4 and ':' not in t and t.isdigit(): # "1400" -> "14:00"
                    t = f"{t[:2]}:{t[2:]}"
                elif len(t) <= 2 and t.isdigit(): # "14" -> "14:00"
                    t = f"{t.zfill(2)}:00"
                return t[:5]

            if time_v:
                try: 
                    t_str = clean_time(time_v)
                    if t_str: e_obj.time = datetime.strptime(t_str, "%H:%M").time()
                except: pass
            if end_v:
                try: 
                    t_str = clean_time(end_v)
                    if t_str: e_obj.end_time = datetime.strptime(t_str, "%H:%M").time()
                except: pass
                
            e_obj.save()

            # Automated Cost Calculation (Precision overwrite for transport)
            if e_obj.type in ['CAR', 'CAMPER'] and e_obj.distance_km > 0:
                # Decide which profile to use
                cons = v1_cons if e_obj.type == 'CAMPER' else v2_cons
                price = diesel_p if (e_obj.type == 'CAMPER') else petrol_p # Simple heuristic: Camper=Diesel, Car=Petrol
                
                calc_cost = (safe_float(e_obj.distance_km) * (safe_float(cons) / 100.0) * safe_float(price))
                # Only overwrite if AI didn't provide any cost or if user wants precision
                if safe_float(e_obj.cost_estimated) <= 0:
                    e_obj.cost_estimated = round(calc_cost, 2)
                    e_obj.save(update_fields=['cost_estimated'])
            
    # Update Trip end date
    if days_data:
        valid_offsets = [d.get('offset', 0) for d in days_data if isinstance(d, dict)]
        if valid_offsets:
            max_offset = max(valid_offsets)
            trip.end_date = start_date + timedelta(days=max_offset)
            trip.save()

    # Handle Global Expenses (e.g. Tolls/Maut)
    from ..models import GlobalExpense
    global_ex = trip_data.get('global_expenses', [])
    for gx in global_ex:
        if not isinstance(gx, dict): continue
        GlobalExpense.objects.create(
            trip=trip,
            title=gx.get('title', 'Ausgabe'),
            expense_type=gx.get('type', 'FEE'),
            unit_price=safe_float(gx.get('cost', 0)),
            units=safe_int(gx.get('units', 1), 1),
            notes=gx.get('notes', 'Importiert von KI')
        )

    # NEW: Handle Food Preferences (Precise Backend Calculation)
    food_prefs = trip_data.get('food_preferences')
    if food_prefs and days_data:
        cooking_ratio = safe_float(food_prefs.get('cooking_ratio', 0))
        dining_ratio = safe_float(food_prefs.get('dining_out_ratio', 0))
        level = food_prefs.get('price_level', 'med').lower()
        
        # Calculate trip duration
        max_offset = max(d.get('offset', 0) for d in days_data)
        total_days = max_offset + 1
        
        # Determine rates from settings
        # Mapping level to setting keys
        suffix = 'low' if level == 'low' else ('high' if level == 'high' else 'med')
        
        rate_self = safe_float(get_setting(f'food_self_{suffix}', '15', user=user))
        rate_out = safe_float(get_setting(f'food_out_{suffix}', '35', user=user))
        
        persons = safe_int(trip.persons_count, 2)
        
        if cooking_ratio > 0:
            units = round(total_days * cooking_ratio, 1)
            if units > 0:
                GlobalExpense.objects.create(
                    trip=trip,
                    title=f"Verpflegung (Selbstversorgung - {int(cooking_ratio*100)}%)",
                    expense_type='FOOD',
                    unit_price=persons * rate_self,
                    units=units,
                    notes=f"Kalkuliert: {total_days} Tage * {int(cooking_ratio*100)}% * {persons} Pers. (@{rate_self}€)",
                    is_auto_calculated=True
                )
                
        if dining_ratio > 0:
            units = round(total_days * dining_ratio, 1)
            if units > 0:
                GlobalExpense.objects.create(
                    trip=trip,
                    title=f"Verpflegung (Restaurant - {int(dining_ratio*100)}%)",
                    expense_type='FOOD',
                    unit_price=persons * rate_out,
                    units=units,
                    notes=f"Kalkuliert: {total_days} Tage * {int(dining_ratio*100)}% * {persons} Pers. (@{rate_out}€)",
                    is_auto_calculated=True
                )
        
    return trip
