from django.db import models
from django.utils.translation import gettext_lazy as _

class Trip(models.Model):
    name = models.CharField(_("Name"), max_length=200)
    start_date = models.DateField(_("Startdatum"), null=True, blank=True)
    end_date = models.DateField(_("Enddatum"), null=True, blank=True)
    base_currency = models.CharField(_("Basis-Währung"), max_length=10, default="EUR")
    local_currency = models.CharField(_("Lokal-Währung"), max_length=10, default="THB")
    persons_count = models.PositiveIntegerField(_("Anzahl Personen"), default=2)
    persons_ages = models.CharField(_("Alter der Personen"), max_length=100, blank=True, help_text=_("Komma-separiert, z.B. '40, 38, 12'"))
    
    class Meta:
        verbose_name = _("Reise")
        verbose_name_plural = _("Reisen")

    def __str__(self):
        return self.name

    @property
    def grouped_stations(self):
        """Groups consecutive days by location to form stations."""
        stations = []
        days = self.days.all().order_by('date')
        if not days:
            return []
        
        current_station = {
            'location': days[0].location,
            'days': [days[0]],
            'nights': 1
        }
        
        for day in days[1:]:
            if day.location == current_station['location']:
                current_station['days'].append(day)
            else:
                current_station['days_count'] = len(current_station['days'])
                current_station['nights_count'] = max(0, current_station['days_count'] - 1)
                stations.append(current_station)
                current_station = {
                    'location': day.location,
                    'days': [day],
                }
        current_station['days_count'] = len(current_station['days'])
        current_station['nights_count'] = max(0, current_station['days_count'] - 1)
        stations.append(current_station)
        return stations

class Day(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="days")
    date = models.DateField(_("Datum"))
    location = models.CharField(_("Ort"), max_length=200)
    
    class Meta:
        ordering = ['date']
        verbose_name = _("Tag")
        verbose_name_plural = _("Tage")

    def __str__(self):
        return f"{self.date}: {self.location}"

    @property
    def hotel(self):
        return self.events.filter(type='HOTEL').first()

    @property
    def flight(self):
        return self.events.filter(type='FLIGHT').first()

    @property
    def transport(self):
        return self.events.filter(type='TRANSPORT').first()

class Event(models.Model):
    TYPE_CHOICES = [
        ('NONE', _('---')),
        ('FLIGHT', _('✈️ Flug')),
        ('HOTEL', _('🏨 Hotel')),
        ('CAMPING', _('⛺ Camping')),
        ('PITCH', _('🚐📍 Stellplatz')),
        ('BUNGALOW', _('🏡 Bungalow')),
        ('CAMPER', _('🚐 Wohnmobil')),
        ('CAR', _('🚗 Auto')),
        ('SCOOTER', _('🛵 Roller')),
        ('BOAT', _('🛥️ Boot')),
        ('FERRY', _('⛴️ Fähre')),
        ('TAXI', _('🚕 Taxi')),
        ('BUS', _('🚌 Bus')),
        ('TRAIN', _('🚆 Zug / Bus')),
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
    voucher = models.FileField(_("Voucher/Anhang"), upload_to="vouchers/", null=True, blank=True)
    
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
    breakfast_cost = models.DecimalField(_("Frühstück Preis"), max_digits=12, decimal_places=2, default=0)

    # Legacy fields
    cost_local = models.DecimalField(_("Kosten lokal (legacy)"), max_digits=12, decimal_places=2, default=0)
    cost_base = models.DecimalField(_("Kosten Basis EUR (legacy)"), max_digits=12, decimal_places=2, default=0)
    
    is_paid = models.BooleanField(_("Bezahlt"), default=False)
    
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
        if self.type in stay_types and ('check-in' in self.title.lower() or 'ankunft' in self.title.lower()):
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
        """Overridden save to handle automatic Check-out creation/update."""
        # Auto-complete/Format titles for better logic recognition
        if self.type == 'RENTAL_CAR':
            if not self.title:
                self.title = "Abholen: Mietwagen"
            elif not self.title.startswith('Abholen:'):
                self.title = f"Abholen: {self.title}"
        elif self.type in ['HOTEL', 'CAMPING', 'PITCH', 'BUNGALOW'] and not self.title:
            self.title = f"{self.get_type_display()} Check-in"
        
        # Save naturally first so we have an ID for relations
        is_new = self.pk is None
        super().save(*args, **kwargs)

        # Automatic Checkout Logic
        if self.is_checkin and self.nights and self.nights > 0:
            from datetime import timedelta
            checkout_date = self.day.date + timedelta(days=self.nights)
            
            # Find the Day object for the checkout
            from .models import Day
            checkout_day, _ = Day.objects.get_or_create(
                trip=self.day.trip, 
                date=checkout_date,
                defaults={'location': self.day.location}
            )

            if self.type == 'RENTAL_CAR':
                checkout_title = self.title.replace('Abholen:', 'Abgeben:')
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
                # Save self again to store the link (prevent recursion with a flag)
                self.save(update_fields=['linked_checkout'])
            else:
                # Update existing checkout
                checkout = self.linked_checkout
                checkout.day = checkout_day
                checkout.title = checkout_title
                checkout.type = self.type
                checkout.location = self.location
                # Clear costs on checkout to avoid double counting
                checkout.cost_booked = 0
                checkout.cost_estimated = 0
                checkout.save()
        
        elif self.linked_checkout and (not self.is_checkin or not self.nights or self.nights <= 0):
            # Cleanup: Delete the checkout if it's no longer needed
            checkout = self.linked_checkout
            self.linked_checkout = None
            self.save(update_fields=['linked_checkout'])
            checkout.delete()

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
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = _("Tagebucheintrag")
        verbose_name_plural = _("Tagebucheinträge")

class DiaryImage(models.Model):
    diary_entry = models.ForeignKey(DiaryEntry, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="diary/")
    caption = models.CharField(max_length=200, blank=True)
    
    class Meta:
        verbose_name = _("Tagebuch Bild")
        verbose_name_plural = _("Tagebuch Bilder")

class TripTemplate(models.Model):
    name = models.CharField(_("Name der Vorlage"), max_length=100)
    preferences = models.TextField(_("Reise-Präferenzen"), help_text=_("Beschreibe hier deine Standard-Wünsche für diese Art von Reise."))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Reise-Vorlage")
        verbose_name_plural = _("Reise-Vorlagen")

    def __str__(self):
        return self.name

class GlobalSetting(models.Model):
    key = models.CharField(max_length=50, unique=True)
    value = models.TextField(blank=True)
    
    class Meta:
        verbose_name = _("Globale Einstellung")
        verbose_name_plural = _("Globale Einstellungen")

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
    voucher = models.FileField(_("Voucher/Anhang"), upload_to="vouchers/", null=True, blank=True)
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

