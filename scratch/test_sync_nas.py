import requests
import re
import json

def test_sync(url):
    print(f"Testing URL: {url}")
    
    match = re.search(r'polarsteps\.com/([^/]+)/(\d+-[^?&]+)', url)
    token_match = re.search(r'[?&]s=([^&]+)', url)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36',
    }
    
    if match:
        username = match.group(1)
        trip_slug = match.group(2)
        token = token_match.group(1) if token_match else None
        
        api_url = f"https://www.polarsteps.com/api/users/by_username/{username}/trips/{trip_slug}"
        params = {'invite_token': token} if token else {}
        
        print(f"API URL: {api_url}")
        print(f"Params: {params}")
        
        try:
            response = requests.get(api_url, params=params, headers=headers, timeout=30)
            print(f"Status Code: {response.status_code}")
            print(f"Content-Type: {response.headers.get('Content-Type')}")
            print(f"Content length: {len(response.text)}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print("SUCCESS! JSON correctly parsed.")
                    print(f"Trip Name: {data.get('name')}")
                except Exception as je:
                    print(f"JSON ERROR: {je}")
                    print(f"Raw Response (first 500 chars): {response.text[:500]}")
            else:
                print(f"API ERROR: {response.text[:100]}")
        except Exception as e:
            print(f"REQUEST ERROR: {e}")
    else:
        print("URL parsing failed.")

if __name__ == "__main__":
    test_sync("https://www.polarsteps.com/BirgitZaiser/24200863-thailand?s=8c3118cf-b652-40be-b343-f597b298e8ed&share_trip_link_variant=V2")
