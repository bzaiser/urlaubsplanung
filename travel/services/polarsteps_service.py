import json
import os
import shutil
from datetime import datetime, date, timedelta
from django.conf import settings
from django.utils.text import slugify
from ..models import Trip, Day, Event, DiaryEntry, DiaryImage

class PolarstepsImporter:
    def __init__(self, export_path):
        self.export_path = export_path
        self.trip_json_path = os.path.join(export_path, 'trip.json')
        
    def run(self):
        if not os.path.exists(self.trip_json_path):
            raise FileNotFoundError(f"trip.json not found at {self.trip_json_path}")
            
        with open(self.trip_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        # 1. Create Trip
        start_date = datetime.fromtimestamp(data['start_date']).date()
        end_date = datetime.fromtimestamp(data['end_date']).date()
        
        trip = Trip.objects.create(
            name=f"{data['name']} (Import)",
            start_date=start_date,
            end_date=end_date
        )
        
        # 2. Process Steps
        all_steps = data.get('all_steps', [])
        # Sort steps by time to ensure days are generated in order
        all_steps.sort(key=lambda x: x['start_time'])
        
        imported_images_count = 0
        
        for step in all_steps:
            step_date = datetime.fromtimestamp(step['start_time']).date()
            loc_name = step['location']['name']
            
            # 2.1 Get or Create Day
            # We use 'station' for your hierarchy: Station - Day - Event
            day, created = Day.objects.get_or_create(
                trip=trip,
                date=step_date,
                defaults={
                    'location': loc_name,
                    'station': loc_name, # This creates the "Station" hierarchy
                    'latitude': step['location'].get('lat'),
                    'longitude': step['location'].get('lon'),
                    'is_geocoded': True
                }
            )
            
            # 2.2 Create Event (Activity) for this step
            event = Event.objects.create(
                day=day,
                title=step['name'] or loc_name,
                type='ACTIVITY',
                time=datetime.fromtimestamp(step['start_time']).time(),
                notes=step.get('description', ''),
                location=loc_name,
                latitude=step['location'].get('lat'),
                longitude=step['location'].get('lon'),
                is_geocoded=True
            )
            
            # 2.3 Create Diary Entry if description exists
            if step.get('description'):
                diary, d_created = DiaryEntry.objects.get_or_create(day=day)
                if d_created:
                    diary.text = step['description']
                else:
                    # Append if multiple steps on same day
                    diary.text += f"\n\n--- {step['name']} ---\n{step['description']}"
                diary.save()
                
                # 2.4 Process Photos for this step
                # Path pattern: {slug}_{id}/photos/
                step_folder_name = f"{step['slug']}_{step['id']}"
                photos_dir = os.path.join(self.export_path, step_folder_name, 'photos')
                
                if os.path.exists(photos_dir):
                    for filename in os.listdir(photos_dir):
                        if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                            source_file = os.path.join(photos_dir, filename)
                            
                            # Determine destination in media/diary/
                            # We prefix with trip_id to avoid collisions
                            dest_filename = f"ps_{trip.id}_{step['id']}_{filename}"
                            relative_dest_path = os.path.join('diary', dest_filename)
                            absolute_dest_path = os.path.join(settings.MEDIA_ROOT, relative_dest_path)
                            
                            os.makedirs(os.path.dirname(absolute_dest_path), exist_ok=True)
                            
                            try:
                                shutil.copy2(source_file, absolute_dest_path)
                                
                                # Create DiaryImage record
                                DiaryImage.objects.create(
                                    diary_entry=diary,
                                    image=relative_dest_path,
                                    caption=step['name'] or ''
                                )
                                imported_images_count += 1
                            except Exception as e:
                                print(f"Error copying {filename}: {e}")
                                
        return trip, len(all_steps), imported_images_count
