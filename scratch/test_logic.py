import os
import django
from datetime import date

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from travel.models import Trip, Day, Event, GlobalExpense
from travel.services import logic_service

def test_logic():
    # Attempt to find a trip or create a dummy one
    trip = Trip.objects.first()
    if not trip:
        print("No trip found to test.")
        return

    print(f"Testing logic for trip: {trip.name}")
    findings = logic_service.check_trip_logic(trip)
    
    for f in findings:
        print(f"- [{f['level'].upper()}] {f['id']}: {f['message']}")

if __name__ == "__main__":
    test_logic()
