import json
import requests
import time
import logging
import re
import os
import google.generativeai as genai
from json_repair import repair_json as pro_repair
from ..models import GlobalSetting

logger = logging.getLogger(__name__)

def get_setting(key, default=''):
    """Helper to fetch settings from the GlobalSetting model."""
    try:
        return GlobalSetting.objects.get(key=key).value
    except:
        return default

def get_best_gemini_model(api_key):
    """Dynamically finds the best available Gemini model for the key."""
    try:
        genai.configure(api_key=api_key)
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        # Preference Order (Moved 1.5 to top because user project has 0-quota for 2.0)
        preferences = [
            'models/gemini-1.5-flash-latest',
            'models/gemini-1.5-flash',
            'models/gemini-2.0-flash',
            'models/gemini-1.5-flash-8b',
        ]
        
        for p in preferences:
            if p in available_models:
                logger.info(f"Using dynamic model selection: {p}")
                return p
        
        # Fallback to the first available if none of our preferences are matched
        if available_models:
            return available_models[0]
            
    except Exception as e:
        logger.error(f"Error listing models: {e}")
        
    return 'models/gemini-1.5-flash' # Hardcoded fallback

def test_ai_connection():
    """Lightweight test using the official SDK."""
    provider = get_setting('active_ai_provider', 'gemini')
    api_key = get_setting('gemini_api_key' if provider == 'gemini' else 'groq_api_key')
    
    if provider != 'ollama' and not api_key:
        return {"error": f"API Key for {provider} missing"}
        
    if provider == 'gemini':
        try:
            model_name = get_best_gemini_model(api_key)
            model = genai.GenerativeModel(model_name)
            response = model.generate_content("Confirm with 'OK'.")
            return {"status": "success", "message": f"{response.text} (Aktiv: {model_name})"}
        except Exception as e:
            err_msg = str(e).replace(api_key, "HIDDEN_KEY")
            return {"error": err_msg}
    elif provider == 'groq':
        # Groq remains via requests (OpenAI-compatible)
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": "Say 'OK' and confirm your model name."}]
        }
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            if response.status_code == 429:
                return {"error": "Rate Limit: Groq ist gerade ausgelastet. Bitte kurz warten."}
            response.raise_for_status()
            text = response.json()['choices'][0]['message']['content']
            return {"status": "success", "message": text}
        except Exception as e:
            err_msg = str(e).replace(api_key, "HIDDEN_KEY")
            return {"error": err_msg}
    elif provider == 'ollama':
        model_name = get_setting('ollama_model_name', 'llama3')
        ollama_url = get_setting('ollama_url', 'http://192.168.123.107:11434').rstrip('/')
        url = f"{ollama_url}/api/chat"
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": "Say 'OK' if you are ready."}],
            "stream": False
        }
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            text = response.json()['message']['content']
            return {"status": "success", "message": f"{text} (Ollama Modell: {model_name})"}
        except Exception as e:
            return {"error": f"Ollama nicht erreichbar unter {url}. Fehler: {str(e)}"}

def generate_itinerary(preferences, start_date=None, days=28, start_location="Zuhause", persons_count=2, persons_ages=""):
    provider = get_setting('active_ai_provider', 'gemini')
    
    v1 = {
        'name': get_setting('vehicle1_name', 'Camper'),
        'consump': get_setting('vehicle1_consumption', '12'),
        'range': get_setting('vehicle1_range', '600'),
        'fuel': get_setting('vehicle1_fuel_type', 'Diesel'),
        'weight': get_setting('vehicle1_weight', '3.5t')
    }
    v2 = {
        'name': get_setting('vehicle2_name', 'PKW'),
        'consump': get_setting('vehicle2_consumption', '7'),
        'range': get_setting('vehicle2_range', '800'),
        'fuel': get_setting('vehicle2_fuel_type', 'Benzin')
    }

    if provider == 'gemini':
        itinerary = gemini_generate(preferences, start_date, days, start_location, v1, v2, persons_count, persons_ages)
    elif provider == 'groq':
        itinerary = groq_generate(preferences, start_date, days, start_location, v1, v2, persons_count, persons_ages)
    else:
        itinerary = ollama_generate(preferences, start_date, days, start_location, v1, v2, persons_count, persons_ages)
        
    return normalize_itinerary(itinerary)

def repair_json(json_str):
    """
    Highly robust JSON repair using the "json-repair" library.
    Handles German decimal commas and LLM truncation/mess.
    """
    if not json_str:
        return "{}"
    
    logger.error(f"DEBUG: repair_json called. Input len: {len(json_str)}")
    
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
        logger.error(f"DEBUG: repair_json finished. Output len: {len(repaired)}")
        return repaired
    except Exception as e:
        logger.error(f"Professional repair failed context: {json_str[:200]}...")
        logger.error(f"Professional repair error: {str(e)}")
        # Fallback
        return json_str

    
    # NEW: Try to parse here just for debugging context if it fails
    try:
        json.loads(json_str)
    except json.JSONDecodeError as e:
        # Show exactly what's wrong in the logs
        context = json_str[max(0, e.pos-60):min(len(json_str), e.pos+60)]
        logger.error(f"DEBUG: JSON still failing at char {e.pos} (Line {e.lineno}, Col {e.colno})")
        logger.error(f"DEBUG: Error context: >>>{context}<<<")
        logger.error(f"DEBUG: Error marker: {' ' * (min(e.pos, 60))}^")
        
    return json_str

def get_itinerary_prompt(preferences, start_date, days, start_location, persons_count, persons_ages):
    """Returns the raw prompt text for manual copy-pasting into external LLMs."""
    v1_name = get_setting('vehicle1_name', 'Camper')
    v1_range = get_setting('vehicle1_range', '400')
    v2_name = get_setting('vehicle2_name', 'PKW')
    
    system_text = (
        "Du bist ein Weltklasse-Reiseplaner. Erstelle einen detaillierten Reiseplan auf DEUTSCH.\n"
        "REIHENFOLGE DER ANTWORT:\n"
        "1. BEGRÜNDUNG: Erkläre kurz deine Wahl der Route und Transportmittel.\n"
        "2. KLARTEXT-VORSCHAU: Zeige den Plan in lesbarer Textform an.\n"
        "3. JSON-DATEN: Gib am Ende den Plan als valides JSON-Objekt aus.\n\n"
        "REGELN:\n"
        "1. SPRACHE: Alles auf DEUTSCH.\n"
        "2. KONKRET: Nenne echte Sehenswürdigkeiten, Hotels und Restaurants. Keine Platzhalter!\n"
        "3. DAUER: Erzeuge EXAKT " + str(days) + " Tage. Ignoriere abweichende Zeitangaben in der Vorlage! Kein Abkürzen!\n"
        "4. FLEXIBILITÄT: Du darfst das Startdatum um +-4 Tage und die Dauer um +-3 Tage variieren, um bessere Flüge/Preise zu finden.\n"
        "5. SICHERHEIT: Bei Flügen KEINE Zwischenlandungen in Krisengebieten!\n"
        "6. LOGISTIK: Berücksichtige den Startort " + start_location + ". Wenn Flüge nötig sind, plane den Weg zum Flughafen ein.\n"
        "7. FAHRZEUGE: Nutze ein " + v1_name + " (Reichweite " + v1_range + "km) NUR, wenn die Reise explizit als Wohnmobil-Tour bezeichnet wird oder das Ziel dafür bekannt ist (z.B. Neuseeland, Island, Roadtrip). In allen anderen Fällen (wie Strand-Bungalow-Urlaub) nutze " + v2_name + ", Roller (SCOOTER), TAXI oder Fähre für Teilstrecken.\n"
        "8. STIL: Bevorzuge Bungalows in Strandnähe, lokale Streetfood-Märkte (RESTAURANT) und Aktivitäten wie Wandern, Tauchen oder Roller-Touren.\n"
        "9. SICHERHEIT: KEINE Bilder, KEINE Google Maps Links, KEINE externen Medien in der Antwort.\n"
        "10. LOGISTIK: Jeder einzelne der " + str(days) + " Tage MUSS mindestens ein Event enthalten (KEINE leeren Tage).\n"
        "11. LOGISTIK: Innerhalb eines Aufenthalts (vom Check-in bis zum Check-out am selben Ort/Hotel) MUSS das Feld 'location' für jeden Tag absolut identisch geschrieben sein (exakte Schreibweise), damit die Gruppierung funktioniert.\n"
        "12. LOGISTIK: Bei JEDEM Transport-Event MUSS ein Feld 'distance_km' (als Zahl) und 'end_time' (Ankunftszeit als HH:MM) vorhanden sein.\n"
        "13. LOGISTIK: Bei JEDER Aktivität MUSS ein Feld 'end_time' (Ende der Aktivität) vorhanden sein.\n"
        "14. LOGISTIK: Bei Flügen/Zügen MUSS ein separates Event für Anfahrt/Check-in (2-3h vorher) eingeplant werden.\n"
        "16. UNTERKÜNFTE: Gruppiere ALLE festen Unterkünfte (Hotel, Bungalow, Airbnb, Ferienhaus) als 'HOTEL'. Nutze 'CAMPING' (Campingplatz) oder 'PITCH' (Stellplatz/Freies Stehen) NUR bei Wohnmobil-Touren.\n"
        "17. VERPFLEGUNG: Wenn Verpflegungswünsche (Selbstkochen vs. Restaurant) vorhanden sind, berechne KEINE Euro-Beträge. Gib stattdessen ein Objekt 'food_preferences' mit den Feldern 'cooking_ratio' (0.0-1.0), 'dining_out_ratio' (0.0-1.0) und 'price_level' ('low', 'med', 'high') aus.\n"
        "18. GLOBAL_EXPENSES: Erfasse NUR zusätzliche Gebühren wie 'Maut', 'Vignette' oder 'Fähre-Pauschale' in der Liste 'global_expenses'. (KEINE Verpflegung hier eintragen!).\n"
        "19. FORMAT (AM ENDE DER ANTWORT ALS JSON):\n"
        "{\n"
        "  \"name\": \"Reise-Titel\",\n"
        "  \"assistant_reasoning\": \"...\",\n"
        "  \"days\": [...],\n"
        "  \"food_preferences\": {\"cooking_ratio\": 0.5, \"dining_out_ratio\": 0.5, \"price_level\": \"med\"},\n"
        "  \"global_expenses\": [{\"title\": \"Maut\", \"type\": \"FEE\", \"cost\": 15}]\n"
        "}"
    )
    user_text = f"Sonderwünsche/Ziel: {preferences}. Starttermin: {start_date}. Dauer: {days} Tage."
    
    return f"{system_text}\n\n{user_text}"

def gemini_generate(preferences, start_date, days, start_location, v1, v2, persons_count, persons_ages):
    api_key = get_setting('gemini_api_key')
    if not api_key:
        return {"error": "Gemini API Key missing"}
    
    system_prompt = (
        "Du bist ein Weltklasse-Reiseplaner. Erstelle einen detaillierten Reiseplan als JSON auf DEUTSCH.\n"
        "REGELN:\n"
        "1. SPRACHE: Antworten müssen komplett auf DEUTSCH sein.\n"
        "2. DAUER: Erzeuge EXAKT " + str(days) + " Tage. Flexibilität: +-4 Tage Start, +-3 Tage Dauer erlaubt.\n"
        "3. LOGISTIK: Berücksichtige Startort " + start_location + ". Bei Flügen MUSS die Anfahrt als eigenes Event davor stehen.\n"
        "4. UNTERKÜNFTE: Erstelle für jeden Aufenthalt ZWEI Events (Check-in, Check-out). Gruppiere Bungalow/Airbnb/Ferienhaus als 'HOTEL'.\n"
        "5. FAHRZEUGE: Nutze ein Wohnmobil NUR bei expliziten Womotouren oder Roadtrips (z.B. NZ, Island). Sonst bevorzuge TAXI, FERRY, SCOOTER oder PKW.\n"
        "6. TYPEN: Nutze EXAKT FLIGHT, HOTEL, CAMPING, PITCH, CAMPER, CAR, SCOOTER, BOAT, FERRY, TAXI, BUS, TRAIN, ACTIVITY, RESTAURANT. (KEIN 'TRANSPORT' nutzen!).\n"
        "7. WICHTIG: Wenn die Reise eine Wohnmobil-Tour ist, MUSS jedes Fahr-Event (Driving) den Typ 'CAMPER' haben (NICHT 'CAR' oder 'TRANSPORT').\n"
        "7. LÜCKENLOS: JEDER der " + str(days) + " Tage muss befüllt sein.\n"
        "8. KONSTANZ: Die 'location' muss während eines Aufenthalts (Check-in bis Check-out) an jedem Tag exakt gleich geschrieben sein.\n"
        "9. DETAILS (PFLICHT): Fülle IMMER 'end_time' (HH:MM) und 'distance_km' (Zahl) aus.\n"
        "10. VERPFLEGUNG: Berechne KEINE Euro-Beträge für Essen. Nutze nur das Objekt 'food_preferences' (ratios: 0.0-1.0, price_level: low/med/high).\n"
        "11. MAUT: Erfasse NUR Gebühren (Maut etc.) in 'global_expenses'.\n"
        "12. FORMAT (NUR JSON):\n"
        "{\n"
        "  \"name\": \"Trip\",\n"
        "  \"days\": [...],\n"
        "  \"food_preferences\": {\"cooking_ratio\": 0.5, \"dining_out_ratio\": 0.5, \"price_level\": \"med\"},\n"
        "  \"global_expenses\": [{\"title\": \"Maut\", \"type\": \"FEE\", \"cost\": 30}]\n"
        "}"
    )
    
    genai.configure(api_key=api_key)
    
    # Context: Food Budgets
    food_ctx = (
        f"Tagessätze (pro Person): Selbstversorgung: Niedrig={get_setting('food_self_low')}€/Med={get_setting('food_self_med')}€/High={get_setting('food_self_high')}€, "
        f"Restaurant: Niedrig={get_setting('food_out_low')}€/Med={get_setting('food_out_med')}€/High={get_setting('food_out_high')}€."
    )
    
    user_prompt = f"Plan: {preferences}. Dauer: {days} Tage. Start: {start_date}. Fahrzeuge: {v1}, {v2}. Personen: {persons_count} ({persons_ages}). {food_ctx}"
    model_name = get_best_gemini_model(api_key)
    model = genai.GenerativeModel(
        model_name,
        generation_config={"response_mime_type": "application/json", "temperature": 0.2, "max_output_tokens": 8192},
        safety_settings=[
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
        ]
    )
    
    max_retries = 5
    for attempt in range(max_retries):
        try:
            # Use repair_json to handle minor formatting errors
            cleaned_text = repair_json(response.text)
            return json.loads(cleaned_text)
        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:
                wait_time = 10 * (attempt + 1)
                logger.warning(f"AI Rate limit hit (429). Waiting {wait_time}s...")
                time.sleep(wait_time)
                continue
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            err_msg = str(e).replace(api_key, "HIDDEN_KEY")
            return {"error": err_msg}

def groq_generate(preferences, start_date, days, start_location, v1, v2, persons_count, persons_ages):
    api_key = get_setting('groq_api_key')
    if not api_key:
        return {"error": "Groq API Key missing"}
    
    system_prompt = (
        "Du bist ein Weltklasse-Reiseplaner. Antworte AUSSCHLIESSLICH im JSON-Format.\n"
        "REGELN: 1. Sprache: DEUTSCH. 2. Dauer: EXAKT " + str(days) + " Tage. 3. Unterkünfte: Alles Feste als 'HOTEL', Womo als 'CAMPING'/'PITCH'. 4. Gebühren: Maut in 'global_expenses'. 5. Verpflegung: Nutze 'food_preferences' (ratios: 0.0-1.0, level: low/med/high).\n"
        "Beispiel: {\"name\": \"...\", \"days\": [...], \"food_preferences\": {\"cooking_ratio\": 0.5, \"dining_out_ratio\": 0.5, \"price_level\": \"med\"}}"
    )
    # Context: Food Budgets
    food_ctx = f"Tagessätze: Selbst: {get_setting('food_self_med')}€, Restaurant: {get_setting('food_out_med')}€."
    user_prompt = f"Plan: {preferences}. Dauer: {days} Tage. Personen: {persons_count}. {food_ctx}"
    
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        "response_format": {"type": "json_object"},
        "temperature": 0.2
    }
    
    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            if response.status_code == 429 and attempt < max_retries - 1:
                wait_time = 10 * (attempt + 1)
                time.sleep(wait_time)
                continue
            response.raise_for_status()
            text = response.json()['choices'][0]['message']['content']
            # Use repair_json for resilience
            cleaned_text = repair_json(text)
            return json.loads(cleaned_text)
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            err_msg = str(e).replace(api_key, "HIDDEN_KEY")
            return {"error": f"Groq Error: {err_msg}"}

def ollama_generate(preferences, start_date, days, start_location, v1, v2, persons_count, persons_ages):
    """Generates an itinerary using a local Ollama instance (e.g. on NAS)."""
    model_name = get_setting('ollama_model_name', 'llama3')
    ollama_url = get_setting('ollama_url', 'http://192.168.123.107:11434').rstrip('/')
    
    system_prompt = (
        "Du bist ein Weltklasse-Reiseplaner. Erstelle einen detaillierten Reiseplan als JSON auf DEUTSCH.\n"
        "REGELN:\n"
        "1. SPRACHE: Antworten müssen komplett auf DEUTSCH sein.\n"
        "2. KONKRET: Nenne echte Sehenswürdigkeiten und Restaurantnamen.\n"
        "3. DAUER: Erzeuge EXAKT " + str(days) + " Tage (Flexibilität: +-4 Tage Start, +-3 Tage Dauer für bessere Flüge erlaubt).\n"
        "5. FAHRZEUGE: Nutze ein Wohnmobil NUR bei expliziten Womotouren oder Roadtrips (z.B. NZ, Island). Sonst bevorzuge TAXI, FERRY, SCOOTER oder PKW.\n"
        "6. UNTERKÜNFTE: Erstelle für jeden Aufenthalt ZWEI Events (Check-in, Check-out). Alles Feste (Airbnb/Bungalow) als 'HOTEL'. Camping als 'CAMPING'/'PITCH'.\n"
        "7. STIL: Lokale Streetfood-Märkte, Natur und Erkundung.\n"
        "8. TYPEN: FLIGHT, HOTEL, CAMPING, PITCH, CAMPER, CAR, SCOOTER, BOAT, FERRY, TAXI, BUS, TRAIN, ACTIVITY, RESTAURANT.\n"
        "9. DETAILS: Fülle IMMER 'end_time', 'detail_info' (Flugnummer!), 'distance_km' und 'booking_reference' aus.\n"
        "10. MAUT: Gebühren/Maut in Liste 'global_expenses' erfassen.\n"
        "11. VERPFLEGUNG: Nutze nur 'food_preferences' (cooking_ratio, dining_out_ratio, price_level) für Essen-Wünsche.\n"
        "12. FORMAT: {\"name\": \"...\", \"days\": [...], \"food_preferences\": {...}, \"global_expenses\": [...]}"
    )
    food_ctx = f"Tagessätze: Selbst: {get_setting('food_self_med')}€, Restaurant: {get_setting('food_out_med')}€."
    user_prompt = f"Plan-Wünsche: {preferences}. Dauer: {days} Tage. Start: {start_date}. {food_ctx}"
    
    url = f"{ollama_url}/api/chat"
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "format": "json",
        "stream": False,
        "options": {
            "num_predict": 8192,
            "temperature": 0.2
        }
    }
    try:
        response = requests.post(url, json=payload, timeout=240)
        response.raise_for_status()
        content = response.json()['message']['content'].strip()
        
        # Use the robust repair utility
        content = repair_json(content)
        return normalize_itinerary(json.loads(content))
    except Exception as e:
        return {"error": f"Ollama Fehler ({url}): {str(e)}"}

def refine_itinerary(current_itinerary, instructions):
    provider = get_setting('active_ai_provider', 'gemini')
    if provider == 'ollama':
        model_name = get_setting('ollama_model_name', 'llama3')
        ollama_url = get_setting('ollama_url', 'http://192.168.123.107:11434').rstrip('/')
        url = f"{ollama_url}/api/chat"
        system_prompt = (
            "Du bist ein Reiseplaner-Experte. Aktualisiere diesen Reiseplan als JSON auf DEUTSCH basierend auf dem Feedback. "
            "Regel: Antworte NUR mit validem JSON auf DEUTSCH."
        )
        user_prompt = f"Aktueller PLAN: {json.dumps(current_itinerary)}\n\nFeedback/Änderung: {instructions}"
        payload = {
            "model": model_name,
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            "format": "json",
            "stream": False
        }
        try:
            response = requests.post(url, json=payload, timeout=180)
            response.raise_for_status()
            content = response.json()['message']['content']
            return normalize_itinerary(json.loads(content))
        except Exception as e:
            return {"error": f"Ollama Fehler ({url}): {str(e)}"}

    api_key_name = 'gemini_api_key' if provider == 'gemini' else 'groq_api_key'
    api_key = get_setting(api_key_name)
    
    if not api_key and provider != 'ollama':
        return {"error": f"{provider.capitalize()} API Key missing"}
    
    system_prompt = "You are an expert travel planner. Update this itinerary as JSON. Output ONLY valid JSON."
    user_prompt = f"Current ITINERARY: {json.dumps(current_itinerary)}\n\nInstructions: {instructions}"
    
    if provider == 'gemini':
        genai.configure(api_key=api_key)
        model_name = get_best_gemini_model(api_key)
        model = genai.GenerativeModel(
            model_name,
            generation_config={"response_mime_type": "application/json"},
            safety_settings=[{"category": c, "threshold": "BLOCK_NONE"} for c in ["HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"]]
        )
        
        max_retries = 5
        for attempt in range(max_retries):
            try:
                response = model.generate_content(f"{system_prompt}\n\n{user_prompt}")
                return json.loads(response.text)
            except Exception as e:
                if "429" in str(e) and attempt < max_retries - 1:
                    time.sleep(10 * (attempt + 1))
                    continue
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                err_msg = str(e).replace(api_key, "HIDDEN_KEY")
                return {"error": err_msg}
    else:
        # Groq (Existing logic simplified)
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "system", "content": system_prompt + " HINWEIS: Antworte im JSON-Format."}, {"role": "user", "content": user_prompt}],
            "response_format": {"type": "json_object"}
        }
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            return json.loads(response.json()['choices'][0]['message']['content'])
        except Exception as e:
            err_msg = str(e).replace(api_key, "HIDDEN_KEY")
            return {"error": err_msg}

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
        data['days'] = [{"location": "Reiseziel", "events": data['events']}]

    # 5. Normalize Days and Events
    if 'days' in data and isinstance(data['days'], list):
        last_location = "Unbekannt"
        for i, day in enumerate(data['days']):
            # Ensure day is a dict, not a string
            if isinstance(day, str):
                day = {"location": day, "events": []}
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
                    if 'location' not in event or not event['location']:
                        event['location'] = event.get('city', event.get('place', event.get('destination', event.get('ort', day['location']))))

                    # Map synonyms for 'cost_estimated'
                    if 'cost_estimated' not in event:
                        event['cost_estimated'] = event.get('cost', event.get('price', event.get('eur', 0)))

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
                        'SIGHTSEEING': 'ACTIVITY', 'MUSEUM': 'ACTIVITY', 'WALK': 'ACTIVITY', 'TOUR': 'ACTIVITY',
                        'FOOD': 'RESTAURANT', 'MEAL': 'RESTAURANT', 'DINNER': 'RESTAURANT', 'LUNCH': 'RESTAURANT', 'BREAKFAST': 'RESTAURANT',
                        'STAY': 'HOTEL', 'SLEEP': 'HOTEL', 'ACCOMMODATION': 'HOTEL', 'AIRBNB': 'HOTEL', 'FERIENHAUS': 'HOTEL', 'BUNGALOW': 'HOTEL',
                        'CAMPINGPLATZ': 'CAMPING', 'STELLPLATZ': 'PITCH', 'SOSTA': 'PITCH', 'AREA SOSTA': 'PITCH', 'CAMPER STOP': 'PITCH',
                        'CAMPING SITE': 'CAMPING', 'HOLIDAY PARK': 'CAMPING', 'DRIVE': 'CAR', 'DRIVING': 'CAR', 'TRAVEL': 'CAR', 'TRANSPORT': 'CAR', 'PKW': 'CAR'
                    }
                    
                    # Apply specific mapping
                    if etype_raw in type_map:
                        event['type'] = type_map[etype_raw]
                    else:
                        # Only use the raw type if it's already one of our known base types
                        allowed = ['FLIGHT', 'HOTEL', 'CAMPING', 'PITCH', 'CAMPER', 'CAR', 'SCOOTER', 'BOAT', 'FERRY', 'TAXI', 'BUS', 'TRAIN', 'ACTIVITY', 'RESTAURANT', 'OTHER', 'FOOD', 'FEE', 'RENTAL']
                        if etype_raw not in allowed:
                            event['type'] = 'OTHER'
                        else:
                            event['type'] = etype_raw

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

def save_itinerary_to_db(trip_data, start_date, persons_count=2, persons_ages=""):
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

    trip = Trip.objects.create(
        name=trip_data.get('name', 'Neue KI Reise'),
        start_date=start_date,
        persons_count=int(persons_count or 2),
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
            location=d_data.get('location', 'Unbekannt')
        )
        
        # Load settings for automated cost calculation
        v1_cons = float(get_setting('vehicle1_consumption', '12'))
        v2_cons = float(get_setting('vehicle2_consumption', '8'))
        diesel_p = float(get_setting('diesel_price', '1.60'))
        petrol_p = float(get_setting('petrol_price', '1.70'))
        
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
                location=e_data.get('location', ''),
                cost_estimated=e_data.get('cost_estimated', 0),
                distance_km=dist_final,
                nights=e_data.get('nights'),
                notes=e_data.get('notes', ''),
                booking_reference=e_data.get('booking_reference', ''),
                detail_info=e_data.get('detail_info', e_data.get('flight_number', ''))
            )
            
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
                
                calc_cost = (float(e_obj.distance_km or 0) * (float(cons) / 100) * float(price))
                # Only overwrite if AI didn't provide any cost or if user wants precision
                if float(e_obj.cost_estimated or 0) <= 0:
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
            unit_price=float(gx.get('cost', 0) or 0),
            units=int(gx.get('units', 1) or 1),
            notes=gx.get('notes', 'Importiert von KI')
        )

    # NEW: Handle Food Preferences (Precise Backend Calculation)
    food_prefs = trip_data.get('food_preferences')
    if food_prefs and days_data:
        cooking_ratio = float(food_prefs.get('cooking_ratio', 0))
        dining_ratio = float(food_prefs.get('dining_out_ratio', 0))
        level = food_prefs.get('price_level', 'med').lower()
        
        # Calculate trip duration
        max_offset = max(d.get('offset', 0) for d in days_data)
        total_days = max_offset + 1
        
        # Determine rates from settings
        # Mapping level to setting keys
        suffix = 'low' if level == 'low' else ('high' if level == 'high' else 'med')
        
        rate_self = float(get_setting(f'food_self_{suffix}', '15'))
        rate_out = float(get_setting(f'food_out_{suffix}', '35'))
        
        persons = int(trip.persons_count or 2)
        
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
