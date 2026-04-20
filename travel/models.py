from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _
from django.conf import settings
import json
import os
from PIL import Image
from PIL.ExifTags import TAGS

class Trip(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="trips", null=True, blank=True)
    name = models.CharField(_("Name"), max_length=200)
    start_date = models.DateField(_("Startdatum"), null=True, blank=True)
    end_date = models.DateField(_("Enddatum"), null=True, blank=True)
    base_currency = models.CharField(_("Basis-Währung"), max_length=10, default="EUR")
    local_currency = models.CharField(_("Lokal-Währung"), max_length=10, default="THB")
    persons_count = models.PositiveIntegerField(_("Anzahl Personen"), default=2)
    persons_ages = models.CharField(_("Alter der Personen"), max_length=100, blank=True, help_text=_("Komma-separiert, z.B. '40, 38, 12'"))
    ui_settings = models.JSONField(_("UI Einstellungen"), default=dict, blank=True)
    polarsteps_id = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("Polarsteps Trip ID"))
    
    class Meta:
        verbose_name = _("Reise")
        verbose_name_plural = _("Reisen")
        constraints = [
            models.UniqueConstraint(fields=['user', 'polarsteps_id'], name='unique_user_polarsteps_trip', condition=models.Q(polarsteps_id__isnull=False))
        ]

    def __str__(self):
        return self.name

    @property
    def grouped_stations(self):
        """Groups consecutive days by their station field (or location as fallback)."""
        stations = []
        days = self.days.all().order_by('date')
        if not days:
            return []
        
        # Helper to get the grouping key for a day
        def get_day_group(day):
            return (day.station or day.location).strip()

        current_group_name = get_day_group(days[0])
        current_station = {
            'location': current_group_name,
            'days': [days[0]],
        }
        
        for day in days[1:]:
            day_group = get_day_group(day)
            if day_group == current_group_name:
                current_station['days'].append(day)
            else:
                current_station['days_count'] = len(current_station['days'])
                current_station['nights_count'] = max(0, current_station['days_count'] - 1)
                stations.append(current_station)
                current_group_name = day_group
                current_station = {
                    'location': current_group_name,
                    'days': [day],
                }
        current_station['days_count'] = len(current_station['days'])
        current_station['nights_count'] = max(0, current_station['days_count'] - 1)
        stations.append(current_station)
        return stations

class Day(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="days")
    date = models.DateField(_("Datum"))
    station = models.CharField(_("Station"), max_length=200, blank=True, help_text=_("Gruppierungs-Name (z.B. 'Anreise' oder 'Palawan')"))
    location = models.CharField(_("Ort"), max_length=200)
    latitude = models.DecimalField(_("Breitengrad"), max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(_("Längengrad"), max_digits=9, decimal_places=6, null=True, blank=True)
    is_geocoded = models.BooleanField(_("Geokodierung versucht"), default=False)
    
    def save(self, *args, **kwargs):
        if self.location:
            self.location = self.location.strip()
            
        if self.pk:
            old_day = Day.objects.get(pk=self.pk)
            if old_day.location != self.location:
                self.latitude = None
                self.longitude = None
                self.is_geocoded = False
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['date']
        verbose_name = _("Tag")
        verbose_name_plural = _("Tage")

    def __str__(self):
        return f"{self.date}: {self.location}"

    @property
    def hotel(self):
        """Returns the first hotel/stay event using cached data if available."""
        events = list(self.events.all())
        hotels = [e for e in events if e.type in ['HOTEL', 'CAMPING', 'PITCH', 'BUNGALOW']]
        return hotels[0] if hotels else None

    @property
    def flight(self):
        """Returns the first flight event using cached data if available."""
        events = list(self.events.all())
        flights = [e for e in events if e.type == 'FLIGHT']
        return flights[0] if flights else None

    @property
    def transport(self):
        """Returns the first transport event using cached data if available."""
        events = list(self.events.all())
        transports = [e for e in events if e.type in ['TRANSPORT', 'CAR', 'CAMPER', 'BOAT', 'FERRY', 'TAXI', 'BUS', 'TRAIN', 'METRO', 'TRAM']]
        return transports[0] if transports else None

    @property
    def first_image_url(self):
        """Returns the URL of the primary diary image or the first one as fallback."""
        if hasattr(self, 'diary'):
            primary = self.diary.images.filter(is_primary=True).first()
            if primary:
                return primary.image.url
            
            first = self.diary.images.first()
            if first:
                return first.image.url
        return None

    @property
    def diary_preview(self):
        """Returns a snippet of the diary text."""
        if hasattr(self, 'diary') and self.diary.text:
            text = self.diary.text
            return (text[:150] + '...') if len(text) > 150 else text
        return None

    @property
    def total_cost(self):
        """Returns the total cost of all events on this day (booked or estimated fallback)."""
        return sum((e.cost_booked if e.cost_booked > 0 else e.cost_estimated) for e in self.events.all())

    @property
    def total_distance(self):
        """Returns the total distance of all events on this day."""
        return sum(e.distance_km or 0 for e in self.events.all())

class Event(models.Model):
    TYPE_CHOICES = [
        ('NONE', _('---')),
        ('FLIGHT', _('✈️ Flug')),
        ('HOTEL', _('🏨 Hotel')),
        ('CAMPING', _('⛺ Campingplatz')),
        ('PITCH', _('🚐📍 Stellplatz')),
        ('BUNGALOW', _('🏡 Bungalow')),
        ('CAMPER', _('🚐 Wohnmobil')),
        ('CAR', _('🚗 Auto')),
        ('SCOOTER', _('🛵 Roller')),
        ('BOAT', _('🛥️ Boot')),
        ('FERRY', _('⛴️ Fähre')),
        ('TAXI', _('🚕 Taxi')),
        ('BUS', _('🚌 Bus')),
        ('TRAIN', _('🚆 Zug / Bahn')),
        ('METRO', _('🚇 Metro / U-Bahn')),
        ('TRAM', _('🚋 Straßenbahn / Tram')),
        ('RENTAL_CAR', _('🔑🚗 Mietwagen')),
        ('ACTIVITY', _('🎒 Aktivität')),
        ('RESTAURANT', _('🍽️ Essen')),
        ('OTHER', _('❓ Sonstiges')),
    ]
    
    day = models.ForeignKey(Day, on_delete=models.CASCADE, related_name="events")
    title = models.CharField(_("Titel"), max_length=200)
    location = models.CharField(_("Ort / Ziel"), max_length=200, blank=True)
    type = models.CharField(_("Typ"), max_length=20, choices=TYPE_CHOICES, default='NONE')
    time = models.TimeField(_("Uhrzeit"), null=True, blank=True)
    end_time = models.TimeField(_("Endzeit"), null=True, blank=True)
    notes = models.TextField(_("Notizen"), blank=True)
    booking_reference = models.CharField(_("Buchungsnummer"), max_length=100, blank=True)
    booking_via = models.CharField(_("Gebucht über"), max_length=100, blank=True)
    booking_url = models.URLField(_("Buchungs-Link"), max_length=500, blank=True)
    detail_info = models.CharField(_("Details (Flug-Nr, Terminal, etc.)"), max_length=255, blank=True)
    
    # Geocoding fields [NEW]
    latitude = models.DecimalField(_("Breitengrad"), max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(_("Längengrad"), max_digits=9, decimal_places=6, null=True, blank=True)
    is_geocoded = models.BooleanField(_("Geokodiert"), default=False)
    
    # Financials and Info from Excel
    meals_info = models.CharField(_("Essen"), max_length=255, blank=True)
    activities_info = models.CharField(_("Ausflüge und Eintritt"), max_length=255, blank=True)
    
    cost_booked = models.DecimalField(_("Preis gebucht"), max_digits=12, decimal_places=2, default=0)
    cost_estimated = models.DecimalField(_("Kosten geschätzt"), max_digits=12, decimal_places=2, default=0)
    cost_per_person = models.DecimalField(_("Pro Nase"), max_digits=12, decimal_places=2, default=0)
    cost_total = models.DecimalField(_("Summe"), max_digits=12, decimal_places=2, default=0)
    cost_actual = models.DecimalField(_("Kosten tatsächlich"), max_digits=12, decimal_places=2, default=0)
    distance_km = models.PositiveIntegerField(_("Entfernung (km)"), null=True, blank=True)
    
    # Stay Logic [NEW]
    nights = models.PositiveIntegerField(_("Nächte"), null=True, blank=True)
    linked_checkout = models.OneToOneField(
        'self', on_delete=models.SET_NULL, null=True, blank=True, 
        related_name="linked_checkin"
    )
    
    # New status tracking fields
    PAYMENT_METHODS = [
        ('NONE', _('---')),
        ('CC', _('Kreditkarte')),
        ('PAYPAL', _('PayPal')),
        ('CASH', _('Bar')),
        ('TRANSFER', _('Überweisung')),
        ('EC', _('EC-Karte')),
    ]
    cancellation_deadline = models.DateField(_("Kostenlos stornierbar bis"), null=True, blank=True)
    payment_method = models.CharField(_("Zahlungsmethode"), max_length=20, choices=PAYMENT_METHODS, default='NONE')
    amount_paid = models.DecimalField(_("Bereits gezahlt"), max_digits=12, decimal_places=2, default=0)
    
    # Breakfast Logic [NEW]
    breakfast_included = models.BooleanField(_("Frühstück inkl."), default=False)
    breakfast_cost = models.DecimalField(_("Frühstück Preis"), max_digits=12, decimal_places=2, default=0, blank=True)

    # Legacy fields
    cost_local = models.DecimalField(_("Kosten lokal (legacy)"), max_digits=12, decimal_places=2, default=0)
    cost_base = models.DecimalField(_("Kosten Basis EUR (legacy)"), max_digits=12, decimal_places=2, default=0)
    
    is_paid = models.BooleanField(_("Bezahlt"), default=False)

    # Internal flag [NEW]
    _skip_automation = False
    
    class Meta:
        ordering = ['time', 'id']
        verbose_name = _("Eintrag")
        verbose_name_plural = _("Einträge")

    def __str__(self):
        return f"{self.get_type_display()}: {self.title}"

    @property
    def is_checkin(self):
        """Identifies if this event is a check-in or pick-up (Abholung)."""
        stay_types = ['HOTEL', 'CAMPING', 'PITCH', 'BUNGALOW']
        if self.type in stay_types:
            # If it's a stay type, it's a check-in UNLESS it's explicitly a check-out
            if self.is_checkout:
                return False
            return True
            
        if self.type == 'RENTAL_CAR' and ('abholung' in self.title.lower() or 'start' in self.title.lower() or 'mietbeginn' in self.title.lower() or 'übernahme' in self.title.lower()):
            return True
        # If type is RENTAL_CAR and it's a new entry without a specific 'drop-off' keyword
        if self.type == 'RENTAL_CAR' and not self.is_checkout and not self.linked_checkout:
            return True
        return False

    @property
    def is_checkout(self):
        """Identifies if this event is a check-out or drop-off (Rückgabe)."""
        keywords = ['check-out', 'rückgabe', 'ende', 'abgabe']
        return any(k in self.title.lower() for k in keywords)

    def save(self, *args, **kwargs):
        """Overridden save to handle automatic Geocoding reset and Check-out creation."""
        if self.location:
            self.location = self.location.strip()

        # Optimize: Only check for changes if it's an update AND we're not skipping
        if self.pk and not self._skip_automation:
            try:
                old_instance = Event.objects.get(pk=self.pk)
                if old_instance.location != self.location:
                    self.latitude = None
                    self.longitude = None
                    self.is_geocoded = False
            except Event.DoesNotExist: pass

        # Recursion and Automation Guard
        if getattr(self, '_saving_internal', False) or self._skip_automation:
            return super().save(*args, **kwargs)

        # Auto-complete/Format titles for better logic recognition
        if self.type == 'RENTAL_CAR':
            if not self.title:
                self.title = "Abholen: Mietwagen"
            elif not self.title.startswith('Abholen:') and not self.is_checkout:
                self.title = f"Abholen: {self.title}"
        elif self.type in ['HOTEL', 'CAMPING', 'PITCH', 'BUNGALOW'] and not self.title:
            self.title = f"{self.get_type_display()} Check-in"
        
        # Initial save
        super().save(*args, **kwargs)

        # Skip automated logic if specifically updating only certain fields (internal updates)
        update_fields = kwargs.get('update_fields')
        if update_fields and 'linked_checkout' in update_fields and len(update_fields) == 1:
            return

        # Automatic Checkout Logic
        if self.is_checkin and self.nights and self.nights > 0:
            self._saving_internal = True
            try:
                from datetime import timedelta
                checkout_date = self.day.date + timedelta(days=self.nights)
                
                from .models import Day
                checkout_day = Day.objects.filter(
                    trip=self.day.trip, 
                    date=checkout_date
                ).first()
                
                if not checkout_day:
                    checkout_day = Day.objects.create(
                        trip=self.day.trip,
                        date=checkout_date,
                        location=self.day.location
                    )

                if self.type == 'RENTAL_CAR':
                    checkout_title = self.title.replace('Abholen:', 'Abgeben:')
                    if 'Abgeben' not in checkout_title:
                        checkout_title = f"Abgeben: {checkout_title}"
                    default_time = "10:00"
                else:
                    checkout_title = self.title.lower().replace('check-in', 'Check-out').title()
                    default_time = self.end_time or "11:00"
                
                if not self.linked_checkout:
                    # Create new checkout
                    checkout = Event.objects.create(
                        day=checkout_day,
                        title=checkout_title,
                        type=self.type,
                        time=default_time,
                        location=self.location,
                        cost_booked=0,
                        cost_estimated=0,
                        notes=f"Automatisch generiert von: {self.title}"
                    )
                    self.linked_checkout = checkout
                    self.save(update_fields=['linked_checkout'])
                else:
                    # Update existing checkout
                    checkout = self.linked_checkout
                    checkout.day = checkout_day
                    checkout.title = checkout_title
                    checkout.type = self.type
                    checkout.location = self.location
                    checkout.cost_booked = 0
                    checkout.cost_estimated = 0
                    checkout.save()
            finally:
                self._saving_internal = False
        
        elif self.linked_checkout and (not self.is_checkin or not self.nights or self.nights <= 0):
            self._saving_internal = True
            try:
                # Cleanup: Delete the checkout if it's no longer needed
                checkout = self.linked_checkout
                self.linked_checkout = None
                self.save(update_fields=['linked_checkout'])
                checkout.delete()
            finally:
                self._saving_internal = False

    def delete(self, *args, **kwargs):
        """Ensure linked events are also deleted (Cascading)."""
        if self.linked_checkout:
            self.linked_checkout.delete()
        super().delete(*args, **kwargs)

    @property
    def duration(self):
        """Calculates duration between time and end_time."""
        if self.time and self.end_time:
            from datetime import datetime, date, timedelta
            d1 = datetime.combine(date.min, self.time)
            d2 = datetime.combine(date.min, self.end_time)
            diff = d2 - d1
            if diff.total_seconds() < 0:
                # Crossed midnight
                diff += timedelta(days=1)
            
            hours, remainder = divmod(int(diff.total_seconds()), 3600)
            minutes = remainder // 60
            if hours > 0:
                return f"{hours}h {minutes}m"
            return f"{minutes}m"
        return None

class DiaryEntry(models.Model):
    day = models.OneToOneField(Day, on_delete=models.CASCADE, related_name="diary")
    text = models.TextField(_("Tagebuch Text"), blank=True)
    polarsteps_step_id = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("Polarsteps Step ID"))
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = _("Tagebucheintrag")
        verbose_name_plural = _("Tagebucheinträge")

class DiaryImage(models.Model):
    diary_entry = models.ForeignKey(DiaryEntry, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="diary/")
    caption = models.CharField(max_length=200, blank=True)
    is_primary = models.BooleanField(default=False)

    @property
    def exif_data(self):
        """Extracts basic EXIF data from the image file."""
        try:
            with Image.open(self.image.path) as img:
                info = img._getexif()
                if not info:
                    return None
                
                exif = {}
                for tag, value in info.items():
                    decoded = TAGS.get(tag, tag)
                    exif[decoded] = value
                
                return {
                    'date': exif.get('DateTimeOriginal') or exif.get('DateTime'),
                    'model': exif.get('Model'),
                    'width': exif.get('ExifImageWidth') or img.width,
                    'height': exif.get('ExifImageHeight') or img.height,
                }
        except Exception:
            return None

    class Meta:
        verbose_name = _("Tagebuch Bild")
        verbose_name_plural = _("Tagebuch Bilder")

class TripTemplate(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="trip_templates", null=True, blank=True)
    name = models.CharField(_("Name der Vorlage"), max_length=100)
    preferences = models.TextField(_("Reise-Präferenzen"), help_text=_("Beschreibe hier deine Standard-Wünsche für diese Art von Reise."))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Reise-Vorlage")
        verbose_name_plural = _("Reise-Vorlagen")

    def __str__(self):
        return self.name

class GlobalSetting(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="settings", null=True, blank=True)
    key = models.CharField(max_length=50)
    value = models.TextField(blank=True)
    
    class Meta:
        verbose_name = _("Einstellung")
        verbose_name_plural = _("Einstellungen")
        unique_together = ('user', 'key')

    def __str__(self):
        return self.key

class GlobalExpense(models.Model):
    TYPE_CHOICES = [
        ('FOOD', _('🍟 Verpflegung')),
        ('RENTAL', _('🛴 Miete (Roller/Surf/etc)')),
        ('RENTAL_CAR', _('🔑🚗 Mietwagen')),
        ('FEE', _('🎟️ Eintritt/Gebühr')),
        ('OTHER', _('📦 Sonstiges')),
    ]
    
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="global_expenses")
    title = models.CharField(_("Titel"), max_length=200)
    expense_type = models.CharField(_("Typ"), max_length=20, choices=TYPE_CHOICES, default='OTHER')
    
    unit_price = models.DecimalField(_("Preis pro Einheit"), max_digits=12, decimal_places=2, default=0)
    units = models.PositiveIntegerField(_("Anzahl Einheiten"), default=1)
    
    total_amount = models.DecimalField(_("Gesamtbetrag"), max_digits=12, decimal_places=2, default=0)
    
    notes = models.TextField(_("Notizen"), blank=True)
    is_auto_calculated = models.BooleanField(_("Automatisch berechnet"), default=False)

    class Meta:
        ordering = ['expense_type', 'id']
        verbose_name = _("Globale Ausgabe")
        verbose_name_plural = _("Globale Ausgaben")

    def save(self, *args, **kwargs):
        try:
            up = float(self.unit_price) if self.unit_price is not None else 0
            un = float(self.units) if self.units is not None else 0
            if up > 0 and un > 0:
                self.total_amount = up * un
        except (ValueError, TypeError):
            pass
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_expense_type_display()}: {self.title}"


class ChecklistCategory(models.Model):
    name = models.CharField(_("Kategorie"), max_length=50)
    icon = models.CharField(_("Icon (Bootstrap)"), max_length=50, default="bi-list-check")
    order = models.PositiveIntegerField(default=10)

    class Meta:
        verbose_name = _("Checklisten-Kategorie")
        verbose_name_plural = _("Checklisten-Kategorien")
        ordering = ['order', 'name']

    def __str__(self):
        return self.name

class ChecklistTemplate(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="checklist_templates", null=True, blank=True)
    name = models.CharField(_("Vorlagen-Name"), max_length=100)
    description = models.TextField(_("Beschreibung"), blank=True)

    class Meta:
        verbose_name = _("Checklisten-Vorlage")
        verbose_name_plural = _("Checklisten-Vorlagen")

    def __str__(self):
        return self.name

class ChecklistItemTemplate(models.Model):
    template = models.ForeignKey(ChecklistTemplate, on_delete=models.CASCADE, related_name="items")
    category = models.ForeignKey(ChecklistCategory, on_delete=models.SET_NULL, null=True, related_name="template_items")
    text = models.CharField(_("Eintrag"), max_length=200)
    due_days_before = models.IntegerField(_("Tage vor Abreise"), default=0)

    class Meta:
        verbose_name = _("Checklisten-Eintrag (Vorlage)")
        verbose_name_plural = _("Checklisten-Einträge (Vorlage)")

class TripChecklist(models.Model):
    trip = models.OneToOneField(Trip, on_delete=models.CASCADE, related_name="checklist")
    template = models.ForeignKey(ChecklistTemplate, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        verbose_name = _("Reise-Checkliste")
        verbose_name_plural = _("Reise-Checklisten")

class TripChecklistItem(models.Model):
    checklist = models.ForeignKey(TripChecklist, on_delete=models.CASCADE, related_name="items")
    category = models.ForeignKey(ChecklistCategory, on_delete=models.SET_NULL, null=True, related_name="trip_items")
    text = models.CharField(_("Eintrag"), max_length=200)
    is_checked = models.BooleanField(default=False)
    due_date = models.DateField(_("Fällig am"), null=True, blank=True)
    is_template_item = models.BooleanField(default=True)

    class Meta:
        verbose_name = _("Reise-Checklisten-Eintrag")
        verbose_name_plural = _("Reise-Checklisten-Einträge")
        ordering = ['is_checked', 'category', 'id']

class TripVoucher(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="vouchers", null=True, blank=True)
    expense = models.ForeignKey(GlobalExpense, on_delete=models.CASCADE, related_name="vouchers", null=True, blank=True)
    file = models.FileField(_("Beleg"), upload_to="vouchers/")
    original_filename = models.CharField(_("Original-Dateiname"), max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Beleg / Anhang")
        verbose_name_plural = _("Belege / Anhänge")

    def __str__(self):
        return self.original_filename or os.path.basename(self.file.name)


# --- Signals for Multi-User Initial Setup ---
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

@receiver(post_save, sender=get_user_model())
def ensure_user_defaults(sender, instance, created, **kwargs):
    """
    When a new user is created, copy settings and templates from the admin 
    (first superuser) to give them a starting point.
    """
    if not created:
        return

    User = get_user_model()
    admin = User.objects.filter(is_superuser=True).order_by('id').first()
    if not admin or admin == instance:
        return

    # 1. Copy GlobalSettings
    admin_settings = GlobalSetting.objects.filter(user=admin)
    for s in admin_settings:
        GlobalSetting.objects.get_or_create(
            user=instance,
            key=s.key,
            defaults={'value': s.value}
        )

    # 2. Copy TripTemplates
    admin_trip_templates = TripTemplate.objects.filter(user=admin)
    for t in admin_trip_templates:
        TripTemplate.objects.create(
            user=instance,
            name=t.name,
            preferences=t.preferences
        )

    # 3. Copy ChecklistTemplates (and items)
    admin_check_templates = ChecklistTemplate.objects.filter(user=admin)
    for ct in admin_check_templates:
        new_ct = ChecklistTemplate.objects.create(
            user=instance,
            name=ct.name,
            description=ct.description
        )
        for item in ct.items.all():
            ChecklistItemTemplate.objects.create(
                template=new_ct,
                category=item.category,
                text=item.text,
                due_days_before=item.due_days_before
            )


@receiver(post_delete, sender=DiaryImage)
def auto_delete_file_on_delete(sender, instance, **kwargs):
    """
    Deletes photo from NAS when the record is deleted,
    but ONLY if no other record is using the same file (Deduplication).
    """
    if instance.image:
        storage = instance.image.storage
        # Check if any OTHER DiaryImage still uses this path
        # (instance is already deleted from DB but exists in memory)
        if not DiaryImage.objects.filter(image=instance.image.name).exists():
            if storage.exists(instance.image.name):
                try:
                    storage.delete(instance.image.name)
                except Exception as e:
                    import logging
                    logger.error(f"Error deleting file {instance.image.name}: {e}")
