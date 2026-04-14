import requests
import sys

def check_models(api_key):
    # Try different versions
    versions = ["v1", "v1beta"]
    for v in versions:
        print(f"Checking version {v}...")
        url = f"https://generativelanguage.googleapis.com/{v}/models?key={api_key}"
        try:
            r = requests.get(url)
            if r.status_code == 200:
                models = r.json().get('models', [])
                print(f"Available models in {v}:")
                for m in models:
                    print(f"  - {m['name']}")
            else:
                print(f"Error {v}: {r.status_code} - {r.text}")
        except Exception as e:
            print(f"Exception {v}: {str(e)}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        check_models(sys.argv[1])
    else:
        print("Usage: python check_models.py <api_key>")
