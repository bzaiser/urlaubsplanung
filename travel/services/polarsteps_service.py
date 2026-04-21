import os
import pickle
import time
import random
import re
import json
import requests
from datetime import datetime, date, time as dt_time
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from PIL import Image
from PIL.ExifTags import TAGS
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
    def sync_from_url(url, user=None, existing_trip=None):
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
            
        return PolarstepsImporter.create_trip_from_json(data, user=user, existing_trip=existing_trip)

    @staticmethod
    def create_trip_from_json(data, user=None, existing_trip=None):
        """
        Creates/Updates trip structure based on JSON data.
        Returns (trip, steps_mapping) where mapping is {step_id: diary_entry_id}
        """
        # Ensure we are looking at the trip data (sometimes it's wrapped in a 'trip' key)
        if 'trip' in data:
            data = data['trip']
            
        # 1. Filter Steps: Only keep those with content (text or media) or boundaries
        raw_steps = data.get('all_steps', [])
        raw_steps.sort(key=lambda x: x.get('start_time', 0))
        
        all_steps = []
        for i, step in enumerate(raw_steps):
            has_content = bool(step.get('description')) or bool(step.get('media'))
            is_boundary = (i == 0 or i == len(raw_steps) - 1)
            if has_content or is_boundary:
                all_steps.append(step)
        
        ps_id = str(data.get('id', 'unknown'))
        trip_name = data.get('name', 'Polarsteps Import')
        
        # 1. Start with existing trip if provided, else find by ps_id, else create
        trip = existing_trip
        if not trip:
            trip = Trip.objects.filter(polarsteps_id=ps_id, user=user).first()
        
        if trip:
            # Sync ps_id if it's new to this trip
            if not trip.polarsteps_id:
                trip.polarsteps_id = ps_id
                trip.save()
            # Cleanup old noisy data (only if not doing a manual folder sync)
            # Actually, we keep cleanup but we make sure the 'create' logic below matches ps IDs
            # PolarstepsImporter.cleanup_noisy_steps(trip)
        
        if not trip:
            start_ts = data.get('start_date', time.time())
            end_ts = data.get('end_date', time.time())
            start_date = datetime.fromtimestamp(start_ts).date()
            end_date = datetime.fromtimestamp(end_ts).date()
            
            trip = Trip.objects.create(
                user=user,
                name=f"{trip_name} (Import)",
                start_date=start_date,
                end_date=end_date,
                polarsteps_id=ps_id
            )
        
        # IMPORTANT: Use the pre-filtered steps from earlier for processing!
        # all_steps was filtered at lines 132-137
        
        steps_mapping = {}
        
        for step in all_steps:
            step_id = str(step.get('id', 'unknown'))
            start_ts = step.get('start_time', time.time())
            step_date = datetime.fromtimestamp(start_ts).date()
            
            # Safe location access
            location_data = step.get('location') or {}
            loc_name = location_data.get('name', 'Unbekannter Ort')
            
            # 1. Day
            day = Day.objects.filter(trip=trip, date=step_date).first()
            if not day:
                day = Day.objects.create(
                    trip=trip,
                    date=step_date,
                    location=loc_name,
                    station=loc_name,
                    latitude=location_data.get('lat'),
                    longitude=location_data.get('lon'),
                    is_geocoded=True
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
                    'is_geocoded': True,
                    'polarsteps_step_id': step_id
                }
            )
            # Ensure ID is set even if event existed
            if not event.polarsteps_step_id:
                event.polarsteps_step_id = step_id
                event.save()
            
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
            
            # 4. Media (Skip thumbnails/remote URLs by default to avoid broken links)
            # The user prefers local high-res uploads.
            # Only sync if explicitly requested or if it's a legacy requirement.
            # We skip it here to keep the DB clean as requested.
            pass
            
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

    @staticmethod
    def cleanup_noisy_steps(trip):
        """
        Removes Events and DiaryEntries that were imported from Polarsteps 
        but have no manual content (no text, no images).
        """
        # Find all diary entries for this trip that have a polarsteps ID
        noisy_entries = DiaryEntry.objects.filter(
            day__trip=trip, 
            polarsteps_step_id__isnull=False
        ).exclude(polarsteps_step_id='')

        for entry in noisy_entries:
            # Only delete if it has NO manual text and NO images
            # (Polarsteps text is okay to delete since we re-sync it)
            if entry.images.count() == 0:
                # Delete associated Event if it's confirmed as a Polarsteps item
                Event.objects.filter(day__trip=trip, polarsteps_step_id=entry.polarsteps_step_id).delete()
                entry.delete()
        
        # Finally, delete ANY Events with a polarsteps_step_id that were NOT in the filtered list
        # (This handles the case where steps were deleted in Polarsteps or no longer meet our filter)
        # But for now, the pre-filtering & delete above is sufficient.

    @staticmethod
    def match_photo_by_exif(trip, photo_file):
        """
        Extracts EXIF time from photo_file and finds the best DiaryEntry in trip.
        Returns the (diary_entry, match_type) or (None, None).
        """
        try:
            with Image.open(photo_file) as img:
                exif_raw = img._getexif()
                if not exif_raw:
                    return None, "no_exif"
                
                exif = {TAGS.get(tag, tag): value for tag, value in exif_raw.items()}
                date_str = exif.get('DateTimeOriginal') or exif.get('DateTime')
                if not date_str:
                    return None, "no_date"
                
                # Format: "YYYY:MM:DD HH:MM:SS"
                dt = datetime.strptime(date_str, '%Y:%m:%d %H:%M:%S')
                photo_date = dt.date()
                photo_time = dt.time()
                
                # 1. Find the day
                day = Day.objects.filter(trip=trip, date=photo_date).first()
                if not day:
                    return None, "day_not_in_trip"
                
                # 2. Find the diary entry (create if missing)
                diary, _ = DiaryEntry.objects.get_or_create(day=day)
                
                # 3. Find the best event on that day
                # We prioritize events that are closest to the photo time
                events = day.events.filter(time__isnull=False).order_by('time')
                best_event = None
                
                if events.exists():
                    import datetime as dt_mod
                    photo_dt = dt_mod.datetime.combine(dt_mod.date.min, photo_time)
                    min_diff = dt_mod.timedelta(hours=24)
                    
                    for event in events:
                        event_dt = dt_mod.datetime.combine(dt_mod.date.min, event.time)
                        diff = abs(photo_dt - event_dt)
                        if diff < min_diff:
                            min_diff = diff
                            best_event = event
                
                return diary, "success"
                
        except Exception as e:
            print(f"EXIF Match Error: {e}")
            return None, "error"
