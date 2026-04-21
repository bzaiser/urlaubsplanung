import re

def clean_test(location_name):
    clean_location = location_name
    
    # Current Split logic
    if '->' in clean_location:
         clean_location = clean_location.split('->')[1].strip() # Check if taking DEST is better
    elif ' - ' in clean_location:
         clean_location = clean_location.split(' - ')[-1].strip()

    # New proposed logic for "zum", "nach", "bis"
    # We want the last part as it is usually the target
    delimiters = [r'\s+zum\s+', r'\s+nach\s+', r'\s+bis\s+', r'\s+zu\s+']
    for sep in delimiters:
        parts = re.split(sep, clean_location, flags=re.IGNORECASE)
        if len(parts) > 1:
            clean_location = parts[-1].strip()
            break
            
    return clean_location

test_strings = [
    "Oberstenfeld zum Toblacher See",
    "Flug von Manila nach Davao",
    "Fahrt bis München",
    "Bungalow am Meer",
    "Stadtrundgang in Paris"
]

for s in test_strings:
    print(f"Original: {s} -> Cleaned: {clean_test(s)}")
