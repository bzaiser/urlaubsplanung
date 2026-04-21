import requests
import re
import json

url = "https://www.polarsteps.com/BirgitZaiser/24200863-thailand?s=8c3118cf-b652-40be-b343-f597b298e8ed&share_trip_link_variant=V2"

# Extract components
# Pattern: polarsteps.com/USERNAME/ID-SLUG
match = re.search(r'polarsteps\.com/([^/]+)/(\d+-[^?]+)', url)
token_match = re.search(r'[?&]s=([^&]+)', url)

if match:
    username = match.group(1)
    trip_slug = match.group(2) # e.g. 24200863-thailand
    token = token_match.group(1) if token_match else None
    
    print(f"Username: {username}")
    print(f"Trip Slug: {trip_slug}")
    print(f"Token: {token}")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    }
    
    # Try slug-based anonymous access
    # Endpoints to try:
    # 1. /api/users/by_username/{username}/trips/{trip_slug}
    # 2. /api/trips/{trip_id} (Wait, we know ID is 24200863)
    
    ps_id = trip_slug.split('-')[0]
    
    # Let's try the absolute raw API endpoint with the token as 'invite_token'
    # but maybe it needs to be part of the URL path? (Less likely but possible)
    
    test_urls = [
        f"https://www.polarsteps.com/api/trips/{ps_id}?invite_token={token}",
        f"https://www.polarsteps.com/api/users/by_username/{username}/trips/{trip_slug}?invite_token={token}",
        f"https://www.polarsteps.com/api/slug/trips/{trip_slug}?invite_token={token}"
    ]
    
    for t_url in test_urls:
        print(f"Trying: {t_url}")
        resp = requests.get(t_url, headers=headers, timeout=30)
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            print(f"SUCCESS with {t_url}!")
            break
    else:
        print("All slug-based attempts failed.")
else:
    print("Failed to parse URL components")
