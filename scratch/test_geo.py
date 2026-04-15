import os
import django
import sys

# Set up Django
sys.path.append('/home/bernd/Documents/dev/urlaubsplanung')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'urlaubsplanung.settings')
django.setup()

from travel.models import Trip
from travel.services.geo_service import geocode_location

trip = Trip.objects.first()
if not trip:
    print("No trips found.")
    sys.exit()

print(f"Testing Trip: {trip.name}")
locations = set(trip.days.values_list('location', flat=True))
for loc in locations:
    lat, lon = geocode_location(loc)
    print(f"Location: '{loc}' -> Lat: {lat}, Lon: {lon}")
