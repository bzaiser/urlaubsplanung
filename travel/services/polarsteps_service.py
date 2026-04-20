import re
import json
import requests
from datetime import datetime
from django.conf import settings
from ..models import Trip, Day, Event, DiaryEntry, DiaryImage

class PolarstepsImporter:
    @staticmethod
    def sync_from_url(url, user=None):
        """
        Parses a Polarsteps URL, identifies the correct API endpoint, and syncs data.
        Supports public trips and private trips with an invite token (s=...).
        """
        import re
        import requests
        
        # 1. Parse URL components
        # Pattern samples: 
        # - https://www.polarsteps.com/BirgitZaiser/24200863-thailand?s=...
        # - https://www.polarsteps.com/BirgitZaiser/24200863-thailand
        match = re.search(r'polarsteps\.com/([^/]+)/(\d+-[^?&]+)', url)
        token_match = re.search(r'[?&]s=([^&]+)', url)
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Referer': 'https://www.polarsteps.com/',
        }
        
        if match:
            username = match.group(1)
            trip_slug = match.group(2)
            token = token_match.group(1) if token_match else None
            
            # Use the robust slug-based endpoint which supports invite tokens
            api_url = f"https://www.polarsteps.com/api/users/by_username/{username}/trips/{trip_slug}"
            params = {'invite_token': token} if token else {}
            
            response = requests.get(api_url, params=params, headers=headers, timeout=30)
        else:
            # Fallback to ID-based if it's just a number
            ps_id_match = re.search(r'/(\d+)', url)
            if ps_id_match:
                ps_id = ps_id_match.group(1)
                api_url = f"https://www.polarsteps.com/api/trips/{ps_id}"
                response = requests.get(api_url, headers=headers, timeout=30)
            else:
                raise Exception("Konnte keine Reise-ID oder Slug aus der URL extrahieren.")

        if response.status_code != 200:
            if response.status_code == 401:
                raise Exception("Zugriff verweigert (401). Ist die Reise privat? Bitte den vollständigen 'Teilen'-Link nutzen.")
            raise Exception(f"Polarsteps API Fehler ({response.status_code}): {response.text[:100]}")
        
        # Diagnostics before parsing
        if 'text/html' in response.headers.get('Content-Type', ''):
            raise Exception("Unerwartete Antwort von Polarsteps: Die API hat eine Webseite statt Daten geschickt. Bitte versuchen Sie es in ein paar Minuten erneut.")

        try:
            data = response.json()
        except Exception:
            raise Exception(f"Fehler beim Verarbeiten der Polarsteps-Daten (Kein gültiges JSON). Empfangen: {response.text[:50]}...")
            
        return PolarstepsImporter.create_trip_from_json(data, user=user)

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
                        separator = f"\n\n--- {step['name'] or loc_name} ---\n"
                        diary.text += separator + desc
                diary.save()
            
            # 4. Media (Links only for sync)
            media_items = step.get('media', [])
            for media in media_items:
                cdn_url = media.get('cdn_path') or media.get('path')
                if cdn_url:
                    # Check if this image link already exists for this entry
                    exists = DiaryImage.objects.filter(diary_entry=diary, remote_url=cdn_url).exists()
                    if not exists:
                        DiaryImage.objects.create(
                            diary_entry=diary,
                            remote_url=cdn_url,
                            caption=media.get('description', '') or ""
                        )
            
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

    @staticmethod
    def archive_all_remote_images(trip):
        """
        Downloads all remote photos into local storage for archiving.
        Useful when back home in WLAN.
        """
        import os
        import requests
        from django.core.files.base import ContentFile
        
        images = DiaryImage.objects.filter(diary_entry__day__trip=trip, image='', remote_url__isnull=False).exclude(remote_url='')
        
        count = 0
        for img in images:
            try:
                response = requests.get(img.remote_url, timeout=30)
                if response.status_code == 200:
                    ext = img.remote_url.split('.')[-1][:4] # simple extension guess
                    if '?' in ext: ext = ext.split('?')[0]
                    filename = f"ps_archive_{img.id}.{ext}"
                    
                    img.image.save(filename, ContentFile(response.content), save=True)
                    count += 1
            except Exception as e:
                print(f"Error archiving image {img.id}: {e}")
                
        return count
