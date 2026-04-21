import requests
import re
import json

def test_cookie_sync(url):
    print(f"Testing Cookie Sync for: {url}")
    
    token_match = re.search(r'[?&]s=([^&]+)', url)
    token = token_match.group(1) if token_match else None
    
    # Extract username and slug
    match = re.search(r'polarsteps\.com/([^/]+)/(\d+-[^?&]+)', url)
    username = match.group(1)
    trip_slug = match.group(2)
    ps_id = trip_slug.split('-')[0]

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36',
        'Accept': 'application/json',
        'Referer': f'https://www.polarsteps.com/{username}/{trip_slug}'
    })

    if token:
        # The magic trick: Set the token as a cookie
        session.cookies.set('invite_token', token, domain='www.polarsteps.com')
        print(f"Cookie 'invite_token' set to {token}")

    # Try different endpoints
    api_url = f"https://www.polarsteps.com/api/users/by_username/{username}/trips/{trip_slug}"
    # Also add it as param just in case
    params = {'invite_token': token} if token else {}
    
    print(f"Calling API: {api_url}")
    try:
        response = session.get(api_url, params=params, timeout=30)
        print(f"Status Code: {response.status_code}")
        print(f"Content-Type: {response.headers.get('Content-Type')}")
        
        if response.status_code == 200 and 'json' in response.headers.get('Content-Type', ''):
            data = response.json()
            print(f"SUCCESS! Received data for trip: {data.get('name')}")
            return True
        else:
            print(f"Failed. Response: {response.text[:200]}")
            return False
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    test_cookie_sync("https://www.polarsteps.com/BirgitZaiser/24200863-thailand?s=8c3118cf-b652-40be-b343-f597b298e8ed&share_trip_link_variant=V2")
