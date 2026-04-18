import requests
import re
import time

def test_geocode(loc_name):
    print(f"\n--- Testing: '{loc_name}' ---")
    
    # Simulate my cleaning logic
    clean = loc_name
    if '->' in clean: clean = clean.split('->')[0].strip()
    clean = re.sub(r'\(.*\)', '', clean).strip()
    clean = re.sub(r'[^\w\s,\-]', '', clean).strip()
    
    prefixes = ['flug nach', 'check-in:', 'check-out:', 'hotel:', 'anfahrt nach']
    for p in prefixes:
        pattern = re.compile(rf'\b{re.escape(p)}\b', re.IGNORECASE)
        clean = pattern.sub('', clean).strip()
    
    print(f"Step 1 (Clean): '{clean}'")
    
    url = "https://nominatim.openstreetmap.org/search"
    headers = {'User-Agent': 'ZaiserUrlaubsplaner/1.5'}
    
    # Try 1: Full cleaned name
    r = requests.get(url, params={'q': clean, 'format': 'json', 'limit': 1}, headers=headers)
    data = r.json()
    if data:
        print(f"RESULT 1: Found! {data[0]['display_name']} -> {data[0]['lat']},{data[0]['lon']}")
        return
    else:
        print("RESULT 1: Not found.")

    # Try 2: Before comma
    if "," in clean:
        simpler = clean.split(',')[0].strip()
        print(f"Step 2 (Simpler): '{simpler}'")
        r = requests.get(url, params={'q': simpler, 'format': 'json', 'limit': 1}, headers=headers)
        data = r.json()
        if data:
            print(f"RESULT 2: Found! {data[0]['display_name']} -> {data[0]['lat']},{data[0]['lon']}")
            return
        else:
            print("RESULT 2: Not found.")

    # Try 3: Add Country (Iberian context)
    for country in ['Portugal', 'Spanien', 'Spain']:
        print(f"Step 3 (Trying with {country}): '{clean}, {country}'")
        r = requests.get(url, params={'q': f"{clean}, {country}", 'format': 'json', 'limit': 1}, headers=headers)
        data = r.json()
        if data:
            print(f"RESULT 3: Found in {country}! {data[0]['display_name']}")
            return

    print("FINAL RESULT: Still nothing. We need a better cleaning logic.")

if __name__ == "__main__":
    # The problematic ones from Bernd's trip
    test_geocode("Nazaré, Mittelportugal")
    test_geocode("Picos de Europa (Avín)")
    test_geocode("Lagos, Algarve")
    test_geocode("Camping Igara (San Sebastián, Spanien)")
