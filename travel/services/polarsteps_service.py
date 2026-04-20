import os
import pickle
import time
import random
import re
import json
import requests
from datetime import datetime
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from ..models import Trip, Day, Event, DiaryEntry, DiaryImage

class PolarstepsImporter:
    COOKIE_FILE = os.path.join(settings.BASE_DIR, '.polarsteps_session.pkl')

    @staticmethod
    def _load_session(session):
        """Loads cookies from a local file into the session."""
        if os.path.exists(PolarstepsImporter.COOKIE_FILE):
            try:
                with open(PolarstepsImporter.COOKIE_FILE, 'rb') as f:
                    session.cookies.update(pickle.load(f))
                return True
            except Exception:
                return False
        return False

    @staticmethod
    def _save_session(session):
        """Saves session cookies to a local file."""
        try:
            with open(PolarstepsImporter.COOKIE_FILE, 'wb') as f:
                pickle.dump(session.cookies, f)
        except Exception:
            pass

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
        
        # 1. Parse URL components
        match = re.search(r'polarsteps\.com/([^/]+)/(\d+-[^?&]+)', url)
        token_match = re.search(r'[?&]s=([^&]+)', url)
        token = token_match.group(1) if token_match else None
        
        # 2. Decide Strategy: "Clean" for public, "Stealth" for private
        if not token:
            # --- STRATEGY A: CLEAN/STANDARD (for public trips) ---
            # Extract ID and use simple request (as it worked initially)
            ps_id_match = re.search(r'/(\d+)', url)
            if ps_id_match:
                ps_id = ps_id_match.group(1)
                api_url = f"https://www.polarsteps.com/api/trips/{ps_id}"
                print(f"Polarsteps: Clean-Sync for public trip {ps_id}")
                try:
                    response = requests.get(api_url, timeout=30)
                except Exception as e:
                    raise Exception(f"Verbindungsfehler (Standard): {str(e)}")
            else:
                raise Exception(_("Konnte keine Reise-ID aus dem öffentlichen Link extrahieren."))
        else:
            # --- STRATEGY B: STEALTH/HACKER (for private trips with token) ---
            print("Polarsteps: Stealth-Sync for private trip with token")
            headers = {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1',
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7',
                'Referer': 'https://www.polarsteps.com/',
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-origin',
            }
            
            session = requests.Session()
            session.headers.update(headers)
            PolarstepsImporter._load_session(session)
            session.cookies.set('invite_token', token, domain='www.polarsteps.com')
            
            username = match.group(1) if match else "user"
            trip_slug = match.group(2) if match else "trip"
            api_url = f"https://www.polarsteps.com/api/users/by_username/{username}/trips/{trip_slug}"
            
            try:
                response = session.get(api_url, params={'invite_token': token}, timeout=30)
            except Exception as e:
                raise Exception(f"Verbindungsfehler (Stealth): {str(e)}")

        # Handle Polarsteps Bot-Wall / Redirection
        if response.status_code == 200 and 'text/html' in response.headers.get('Content-Type', ''):
            raise Exception(_("Polarsteps blockiert gerade den automatischen Zugriff. Bitte versuchen Sie es später noch einmal oder stellen Sie die Reise kurzzeitig auf 'Öffentlich'."))

        if response.status_code != 200:
            if response.status_code == 401:
                raise Exception(_("Zugriff verweigert (401). Bitte prüfen Sie den 'Teilen'-Link."))
            raise Exception(f"Polarsteps Fehler ({response.status_code})")
        
        try:
            data = response.json()
            if token: # Only save session if it was a stealth sync
                PolarstepsImporter._save_session(session)
        except Exception:
            raise Exception(_("Fehler beim Verarbeiten der Polarsteps-Daten."))
            
        return PolarstepsImporter.create_trip_from_json(data, user=user)

    @staticmethod
    def create_trip_from_json(data, user=None):
        """
        Creates/Updates trip structure based on JSON data.
        Returns (trip, steps_mapping) where mapping is {step_id: diary_entry_id}
        """
        # Ensure we are looking at the trip data (sometimes it's wrapped in a 'trip' key)
        if 'trip' in data:
            data = data['trip']
            
        ps_id = str(data.get('id', 'unknown'))
        trip_name = data.get('name', 'Polarsteps Import')
        
        # Safe timestamp conversion
        start_ts = data.get('start_date', time.time())
        end_ts = data.get('end_date', time.time())
        
        start_date = datetime.fromtimestamp(start_ts).date()
        end_date = datetime.fromtimestamp(end_ts).date()
        
        # Smart Check: Does this trip already exist?
        trip = Trip.objects.filter(polarsteps_id=ps_id, user=user).first()
        
        if not trip:
            trip = Trip.objects.create(
                user=user,
                name=f"{trip_name} (Import)",
                start_date=start_date,
                end_date=end_date,
                polarsteps_id=ps_id
            )
        
        all_steps = data.get('all_steps', [])
        all_steps.sort(key=lambda x: x['start_time'])
        
        steps_mapping = {}
        
        for step in all_steps:
            step_id = str(step.get('id', 'unknown'))
            start_ts = step.get('start_time', time.time())
            step_date = datetime.fromtimestamp(start_ts).date()
            
            # Safe location access
            location_data = step.get('location') or {}
            loc_name = location_data.get('name', 'Unbekannter Ort')
            
            # 1. Day
            day, created = Day.objects.get_or_create(
                trip=trip,
                date=step_date,
                defaults={
                    'location': loc_name,
                    'station': loc_name,
                    'latitude': location_data.get('lat'),
                    'longitude': location_data.get('lon'),
                    'is_geocoded': True
                }
            )
            
            # 2. Event (Deduplicate based on title and time if possible)
            ev_title = step.get('name') or loc_name
            ev_time = datetime.fromtimestamp(start_ts).time()
            event, ev_created = Event.objects.get_or_create(
                day=day,
                title=ev_title,
                time=ev_time,
                defaults={
                    'type': 'ACTIVITY',
                    'notes': step.get('description', ''),
                    'location': loc_name,
                    'latitude': location_data.get('lat'),
                    'longitude': location_data.get('lon'),
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
