import os
import django
import sys

# Set up Django environment
sys.path.append('/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from travel.models import Trip, ChecklistCategory, TripChecklist, TripChecklistItem
from travel.views import trip_checklist
from django.test import RequestFactory
from django.urls import reverse

def test():
    try:
        trip = Trip.objects.first()
        if not trip:
            print("No trip found")
            return
            
        print(f"Testing checklist view for trip: {trip.name}")
        
        factory = RequestFactory()
        request = factory.get(reverse('travel:trip_checklist', args=[trip.id]))
        # Manually add session if needed, but the view uses it
        request.session = {} 
        
        response = trip_checklist(request, trip.id)
        print(f"Response status: {response.status_code}")
        
        if response.status_code != 200:
            print("Error: View failed")
            
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test()
