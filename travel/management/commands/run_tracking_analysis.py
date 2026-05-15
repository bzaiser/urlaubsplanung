from django.core.management.base import BaseCommand
from travel.services.tracking_service import TrackingProcessor

class Command(BaseCommand):
    help = 'Runs the automatic tracking point analysis and generates suggestions'

    def handle(self, *args, **options):
        self.stdout.write("Starting tracking analysis...")
        count = TrackingProcessor.process_raw_points()
        self.stdout.write(self.style.SUCCESS(f"Successfully generated {count} new tracking suggestions."))
