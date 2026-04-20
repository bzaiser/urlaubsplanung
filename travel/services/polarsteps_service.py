import os
import shutil
from datetime import datetime
from django.conf import settings
from ..models import Trip, Day, Event, DiaryEntry, DiaryImage

class PolarstepsImporter:
    @staticmethod
    def create_trip_from_json(data, user=None):
        """
        Creates trip structure based on JSON data.
        Returns (trip, steps_mapping) where mapping is {step_id: diary_entry_id}
        """
        ps_id = str(data.get('id'))
        
        # Smart Check: Does this trip already exist?
        existing_trip = Trip.objects.filter(ui_settings__polarsteps_id=ps_id, user=user).first()
        if existing_trip:
            # Reconstruct mapping for existing trip (based on diary entries text or previous imports)
            # For simplicity, we create a new one if user explicitly re-imports, 
            # BUT we will deduplicate the photos below.
            pass

        start_date = datetime.fromtimestamp(data['start_date']).date()
        end_date = datetime.fromtimestamp(data['end_date']).date()
        
        trip = Trip.objects.create(
            user=user,
            name=f"{data['name']} (Import)",
            start_date=start_date,
            end_date=end_date,
            ui_settings={'polarsteps_id': ps_id}
        )
        
        all_steps = data.get('all_steps', [])
        all_steps.sort(key=lambda x: x['start_time'])
        
        steps_mapping = {}
        
        for step in all_steps:
            step_date = datetime.fromtimestamp(step['start_time']).date()
            loc_name = step['location']['name']
            
            # Use 'station' for hierarchy: Station - Day - Event
            day, created = Day.objects.get_or_create(
                trip=trip,
                date=step_date,
                defaults={
                    'location': loc_name,
                    'station': loc_name,
                    'latitude': step['location'].get('lat'),
                    'longitude': step['location'].get('lon'),
                    'is_geocoded': True
                }
            )
            
            # Create Event (Activity)
            Event.objects.create(
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
            
            # Diary Entry
            diary, d_created = DiaryEntry.objects.get_or_create(day=day)
            desc = step.get('description', '')
            if d_created:
                diary.text = desc
            elif desc:
                diary.text += f"\n\n--- {step['name']} ---\n{desc}"
            diary.save()
            
            steps_mapping[str(step['id'])] = diary.id
            
        return trip, steps_mapping

    @staticmethod
    def save_photo(diary_entry_id, photo_file, step_id, original_filename):
        """
        Saves a single uploaded photo to the diary entry, with deduplication.
        """
        diary = DiaryEntry.objects.get(id=diary_entry_id)
        
        # STABLE FILENAME for deduplication: fixed prefix + step_id + filename
        dest_filename = f"ps_step_{step_id}_{original_filename}"
        relative_dest_path = os.path.join('diary', dest_filename)
        absolute_dest_path = os.path.join(settings.MEDIA_ROOT, relative_dest_path)
        
        # SMART CHECK: If file exists, don't copy again!
        if not os.path.exists(absolute_dest_path):
            os.makedirs(os.path.dirname(absolute_dest_path), exist_ok=True)
            with open(absolute_dest_path, 'wb+') as destination:
                for chunk in photo_file.chunks():
                    destination.write(chunk)
                
        # Create DiaryImage record (linked to the shared file)
        return DiaryImage.objects.create(
            diary_entry=diary,
            image=relative_dest_path
        )
