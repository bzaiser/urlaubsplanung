from django.db import models
from django.utils.translation import gettext_lazy as _

class Trip(models.Model):
    name = models.CharField(_("Name"), max_length=200)
    start_date = models.DateField(_("Startdatum"), null=True, blank=True)
    end_date = models.DateField(_("Enddatum"), null=True, blank=True)
    base_currency = models.CharField(_("Basis-Währung"), max_length=10, default="EUR")
    local_currency = models.CharField(_("Lokal-Währung"), max_length=10, default="THB")
    
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
                current_station['nights'] += 1
            else:
                stations.append(current_station)
                current_station = {
                    'location': day.location,
                    'days': [day],
                    'nights': 1
                }
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
        ('FLIGHT', _('Flug')),
        ('HOTEL', _('Unterkunft')),
        ('ACTIVITY', _('Aktivität')),
        ('TRANSPORT', _('Transport')),
        ('OTHER', _('Sonstiges')),
    ]
    
    day = models.ForeignKey(Day, on_delete=models.CASCADE, related_name="events")
    title = models.CharField(_("Titel"), max_length=200)
    type = models.CharField(_("Typ"), max_length=20, choices=TYPE_CHOICES, default='ACTIVITY')
    time = models.TimeField(_("Uhrzeit"), null=True, blank=True)
    end_time = models.TimeField(_("Endzeit"), null=True, blank=True)
    notes = models.TextField(_("Notizen"), blank=True)
    booking_reference = models.CharField(_("Buchungsnummer"), max_length=100, blank=True)
    booking_via = models.CharField(_("Gebucht über"), max_length=100, blank=True)
    detail_info = models.CharField(_("Details (Flug-Nr, Terminal, etc.)"), max_length=255, blank=True)
    voucher = models.FileField(_("Voucher/Anhang"), upload_to="vouchers/", null=True, blank=True)
    
    # Financials
    cost_local = models.DecimalField(_("Kosten lokal"), max_digits=12, decimal_places=2, default=0)
    cost_base = models.DecimalField(_("Kosten Basis (EUR)"), max_digits=12, decimal_places=2, default=0)
    is_paid = models.BooleanField(_("Bezahlt"), default=False)
    
    class Meta:
        ordering = ['time', 'id']
        verbose_name = _("Event")
        verbose_name_plural = _("Events")

    def __str__(self):
        return f"{self.get_type_display()}: {self.title}"

    @property
    def duration(self):
        """Calculates duration between time and end_time."""
        if self.time and self.end_time:
            from datetime import datetime, combine, date
            d1 = combine(date.min, self.time)
            d2 = combine(date.min, self.end_time)
            diff = d2 - d1
            if diff.total_seconds() < 0:
                return None # Overnight not handled yet simple
            
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
