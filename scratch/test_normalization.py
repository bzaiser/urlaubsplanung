
import sys
import os
import json

# Add project root to path
sys.path.append('/home/bernd/Documents/dev/urlaubsplanung')

# Setup Django
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'urlaubsplanung.settings')
django.setup()

from travel.services import ai_service

def test_normalization(data, label):
    print(f"\n--- Testing: {label} ---")
    try:
        result = ai_service.normalize_itinerary(data)
        print(f"Success! Keys: {list(result.keys())}")
        if 'days' in result:
            print(f"Days count: {len(result['days'])}")
        if 'error' in result:
            print(f"Error caught: {result['error']}")
    except Exception as e:
        print(f"CRASH: {str(e)}")

# Test Case 1: Direct Error
test_normalization({"error": "LLM failed"}, "Raw Error Dictionary")

# Test Case 2: Malformed Days (Dict instead of List)
test_normalization({"days": {"1": {"location": "A"}, "2": {"location": "B"}}}, "Days as Dict")

# Test Case 3: Empty Object
test_normalization({}, "Empty Object")

# Test Case 4: Only Events
test_normalization({"events": [{"title": "Event 1"}]}, "Only Events")

# Test Case 5: Nested Itinerary List
test_normalization({"itinerary": [{"location": "X"}]}, "Nested Itinerary List")

# Test Case 6: None
test_normalization(None, "None")
