import requests

# The exact combination that worked in Test 4
url = "https://www.polarsteps.com/api/users/by_username/BirgitZaiser/trips/24200863-thailand?invite_token=8c3118cf-b652-40be-b343-f597b298e8ed"
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
}

print(f"Retrying the EXACT successful call: {url}")
try:
    resp = requests.get(url, headers=headers, timeout=30)
    print(f"Status: {resp.status_code}")
    print(f"Content-Type: {resp.headers.get('Content-Type')}")
    if resp.status_code == 200 and 'json' in resp.headers.get('Content-Type', '').lower():
        data = resp.json()
        print(f"GOLD! It works again. Trip: {data.get('name')}")
    else:
        print(f"Failed. Response snippet: {resp.text[:200]}")
except Exception as e:
    print(f"Error: {e}")
