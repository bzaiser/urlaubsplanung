import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from travel.models import Day, Trip

def cleanup_duplicate_days():
    print("Starting duplicate day cleanup...")
    trips = Trip.objects.all()
    total_deleted = 0
    
    for trip in trips:
        # Get all dates for this trip that have more than one Day object
        duplicate_dates = []
        from django.db.models import Count
        date_counts = Day.objects.filter(trip=trip).values('date').annotate(count=Count('id')).filter(count__gt=1)
        
        for entry in date_counts:
            date = entry['date']
            days = list(Day.objects.filter(trip=trip, date=date).order_by('id'))
            
            # Keep the first one, delete the rest
            keep_day = days[0]
            delete_days = days[1:]
            
            print(f"  Trip '{trip.title}' - Date {date}: found {len(days)} days. Keeping ID {keep_day.id}, deleting {len(delete_days)} others.")
            
            for d in delete_days:
                # Move any events/expenses from the duplicate day to the kept day if necessary
                # (Normally the check-in logic might have linked to the 'wrong' one)
                d.events.all().update(day=keep_day)
                d.delete()
                total_deleted += 1
                
    print(f"Cleanup finished. Total duplicate days removed: {total_deleted}")

if __name__ == "__main__":
    cleanup_duplicate_days()
