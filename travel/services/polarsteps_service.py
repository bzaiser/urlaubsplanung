import os
import shutil
from datetime import datetime
from django.conf import settings
from ..models import Trip, Day, Event, DiaryEntry, DiaryImage

class PolarstepsImporter:
    @staticmethod
    def create_trip_from_json(data, user=None):
        """
        Creates/Updates trip structure based on JSON data.
        Returns (trip, steps_mapping) where mapping is {step_id: diary_entry_id}
        """
        ps_id = str(data.get('id'))
        
        # Smart Check: Does this trip already exist?
        trip = Trip.objects.filter(polarsteps_id=ps_id, user=user).first()
        
        start_date = datetime.fromtimestamp(data['start_date']).date()
        end_date = datetime.fromtimestamp(data['end_date']).date()
        
        if not trip:
            trip = Trip.objects.create(
                user=user,
                name=f"{data['name']} (Import)",
                start_date=start_date,
                end_date=end_date,
                polarsteps_id=ps_id
            )
        
        all_steps = data.get('all_steps', [])
        all_steps.sort(key=lambda x: x['start_time'])
        
        steps_mapping = {}
        
        for step in all_steps:
            step_id = str(step['id'])
            step_date = datetime.fromtimestamp(step['start_time']).date()
            loc_name = step['location'].get('name', 'Unbekannter Ort')
            
            # 1. Day
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
            
            # 2. Event (Deduplicate based on title and time if possible)
            ev_title = step['name'] or loc_name
            ev_time = datetime.fromtimestamp(step['start_time']).time()
            event, ev_created = Event.objects.get_or_create(
                day=day,
                title=ev_title,
                time=ev_time,
                defaults={
                    'type': 'ACTIVITY',
                    'notes': step.get('description', ''),
                    'location': loc_name,
                    'latitude': step['location'].get('lat'),
                    'longitude': step['location'].get('lon'),
                    'is_geocoded': True
                }
            )
            
            # 3. Diary Entry (Deduplicate based on polarsteps_step_id)
            diary = DiaryEntry.objects.filter(day__trip=trip, polarsteps_step_id=step_id).first()
            if not diary:
                diary, d_created = DiaryEntry.objects.get_or_create(day=day)
                diary.polarsteps_step_id = step_id
                desc = step.get('description', '')
                if d_created:
                    diary.text = desc
                else:
                    # If entry already existed for that day but wasn't marked as this step, append
                    if desc and desc not in diary.text:
                        diary.text += f"\n\n--- {step['name']} ---\n{desc}"
                diary.save()
            
            steps_mapping[step_id] = diary.id
            
        return trip, steps_mapping

    @staticmethod
    def save_photo(diary_entry_id, photo_file, step_id, original_filename):
        """
        Saves a single uploaded photo to the diary entry, with extreme deduplication.
        """
        diary = DiaryEntry.objects.get(id=diary_entry_id)
        
        # STABLE FILENAME for deduplication
        dest_filename = f"ps_step_{step_id}_{original_filename}"
        relative_dest_path = os.path.join('diary', dest_filename)
        absolute_dest_path = os.path.join(settings.MEDIA_ROOT, relative_dest_path)
        
        # 1. DB CHECK: Does this image record already exist for this entry?
        existing_img = DiaryImage.objects.filter(diary_entry=diary, image=relative_dest_path).first()
        if existing_img:
            return existing_img

        # 2. DISK CHECK: If file exists but NO record, skip only the writing part
        if not os.path.exists(absolute_dest_path):
            os.makedirs(os.path.dirname(absolute_dest_path), exist_ok=True)
            with open(absolute_dest_path, 'wb+') as destination:
                for chunk in photo_file.chunks():
                    destination.write(chunk)
                
        # 3. Create DiaryImage record
        return DiaryImage.objects.create(
            diary_entry=diary,
            image=relative_dest_path,
            caption=original_filename
        )
