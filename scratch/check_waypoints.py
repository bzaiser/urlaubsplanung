import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from travel.models import Trip
from travel.views import _date # If possible, or just mock it

trip = Trip.objects.latest('id')
print(f"Trip: {trip.name}")

map_data = []
for d_idx, day in enumerate(trip.days.all().order_by('date'), 1):
    if day.latitude and day.longitude:
        map_data.append({'loc': day.location, 'lat': float(day.latitude), 'lon': float(day.longitude), 'is_ev': False})
    for e_idx, ev in enumerate(day.events.all(), 1):
        if ev.latitude and ev.longitude:
            map_data.append({'loc': ev.location, 'lat': float(ev.latitude), 'lon': float(ev.longitude), 'is_ev': True})

print(f"Total waypoints for story: {len(map_data)}")
for i, wp in enumerate(map_data):
    print(f"{i}: {wp['loc']} ({wp['lat']}, {wp['lon']}) {'(Event)' if wp['is_ev'] else ''}")
