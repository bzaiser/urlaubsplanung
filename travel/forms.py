from django import forms
from .models import Trip, Event, Day

class TripForm(forms.ModelForm):
    class Meta:
        model = Trip
        fields = ['name', 'start_date', 'end_date', 'base_currency', 'local_currency']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }

class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ['title', 'type', 'time', 'end_time', 'notes', 'booking_reference', 'booking_via', 'booking_url', 'cost_local', 'is_paid']
        widgets = {
            'time': forms.TimeInput(attrs={'type': 'time', 'class': 'flatpickr-time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time', 'class': 'flatpickr-time'}),
        }

