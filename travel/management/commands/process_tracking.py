from django.core.management.base import BaseCommand
from travel.services.tracking_service import TrackingProcessor

class Command(BaseCommand):
    help = 'Processes raw tracking points and generates intelligent suggestions'

    def handle(self, *args, **options):
        self.stdout.write("Starting tracking point processing...")
        
        try:
            suggestions_created = TrackingProcessor.process_raw_points()
            if suggestions_created > 0:
                self.stdout.write(self.style.SUCCESS(f'Successfully created {suggestions_created} new suggestions!'))
            else:
                self.stdout.write('No new raw points to process or no stays detected.')
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error processing tracking points: {e}'))
