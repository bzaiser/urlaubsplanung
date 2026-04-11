from django import medical
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
        fields = ['title', 'type', 'time', 'notes', 'booking_reference', 'cost_local', 'is_paid']
        widgets = {
            'time': forms.TimeInput(attrs={'type': 'time'}),
        }
