import requests
import re
import json

url = "https://www.polarsteps.com/BirgitZaiser/24200863-thailand?s=8c3118cf-b652-40be-b343-f597b298e8ed&share_trip_link_variant=V2"

print(f"Fetching full HTML as browser: {url}")
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7',
}

session = requests.Session()
response = session.get(url, headers=headers, timeout=30)
print(f"Status Code: {response.status_code}")

if response.status_code == 200:
    content = response.text
    print(f"HTML Length: {len(content)}")
    
    # Check for common Polarsteps data markers in JS
    markers = ['all_steps', 'trip', 'initialState', 'user_id']
    for marker in markers:
        if marker in content:
            print(f"Found marker: '{marker}'")
            
    # Try to extract the JSON block
    # Polarsteps often uses: window.__INITIAL_STATE__ = {...}
    match = re.search(r'__INITIAL_STATE__\s*=\s*(.*?});', content, re.DOTALL)
    if not match:
        # Alternative pattern
        match = re.search(r'initial_state\s*=\s*(.*?});', content, re.DOTALL)
        
    if match:
        print("FOUND INITIAL STATE JSON!")
        try:
            data_str = match.group(1)
            # Basic cleanup if needed
            data = json.loads(data_str)
            print("Successfully parsed large JSON block.")
            # Let's see if we find the trip data inside
            # In some versions it's in data['trip'] or similar
            print(f"Keys in JSON: {list(data.keys())[:10]}")
        except Exception as e:
            print(f"JSON Parse Error: {e}")
            print(f"Snippet: {match.group(1)[:200]}")
    else:
        print(content)
        # Final desperate search for any script tag with 'all_steps'
        script_match = re.search(r'<script.*?>.*?"all_steps".*?</script>', content, re.DOTALL)
        if script_match:
             print("Found a script tag containing 'all_steps'!")
             # Extract and print just a bit of it for analysis
             snippet = script_match.group(0)
             print(f"Snippet: {snippet[:200]}...")
else:
    print(f"Failed to load page: {response.status_code}")
