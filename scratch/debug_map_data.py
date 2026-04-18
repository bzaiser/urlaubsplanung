import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from travel.models import Trip, Event
from django.core.serializers.json import DjangoJSONEncoder

def debug_trip(trip_id):
    active_trip = Trip.objects.filter(id=trip_id).first()
    if not active_trip:
        print(f"Trip {trip_id} not found.")
        return

    print(f"Debugging Trip: {active_trip.name} (ID: {active_trip.id})")
    print(f"Grouped Stations: {len(active_trip.grouped_stations)}")
    
    map_data = []
    for i, station in enumerate(active_trip.grouped_stations, 1):
        found_station_coords = False
        # Check for travel events
        for day in station['days']:
            travel_events = day.events.filter(
                type__in=['FLIGHT', 'TRAIN', 'FERRY', 'BUS', 'CAR']
            ).order_by('time', 'id')
            
            for ev in travel_events:
                if ev.latitude and ev.longitude:
                    print(f"  [EVENT] {ev.location} HAS COORDS: {ev.latitude}, {ev.longitude}")
                    map_data.append({'loc': ev.location, 'type': 'event'})

        # Check main station
        first_day = station['days'][0]
        if first_day.latitude and first_day.longitude:
            print(f"  [STATION] {station['location']} HAS COORDS: {first_day.latitude}, {first_day.longitude}")
            map_data.append({'loc': station['location'], 'type': 'station'})
            found_station_coords = True
        else:
            print(f"  [STATION] {station['location']} NO COORDS on first day ({first_day.date})")
            # Deep check: does ANY day in this station have coords?
            for d in station['days']:
                if d.latitude and d.longitude:
                    print(f"    !!! WARNING: Day {d.date} has coords, but views.py ONLY checks the first day!")

    print(f"\nFinal Map Data Count: {len(map_data)}")
    if len(map_data) == 0:
        print("RESULT: map_data is EMPTY -> This triggers the Loading Screen.")

if __name__ == "__main__":
    debug_trip(7)
