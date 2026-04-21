import requests
import re

url = "https://www.polarsteps.com/BirgitZaiser/24200863-thailand?s=8c3118cf-b652-40be-b343-f597b298e8ed&share_trip_link_variant=V2"

session = requests.Session()
headers = {
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
}

print(f"Checking landing page for cookies: {url}")
resp = session.get(url, headers=headers, timeout=30)
print(f"Status: {resp.status_code}")
print(f"Headers Set-Cookie: {resp.headers.get('Set-Cookie')}")
print(f"Cookies in jar: {session.cookies.get_dict()}")

# Sometimes the token is set as a specific cookie like 'ps_invite_token'
if 'invite_token' in resp.text:
    print("Found 'invite_token' mention in HTML text.")
