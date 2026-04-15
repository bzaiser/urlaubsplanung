from django import forms
from .models import Trip, Event, Day, DiaryEntry, DiaryImage
from django.forms import inlineformset_factory

class TripForm(forms.ModelForm):
    name = forms.CharField(initial="Neue Leere Reise", label="Name")
    
    class Meta:
        model = Trip
        fields = ['name', 'start_date', 'end_date', 'base_currency', 'local_currency', 'persons_count']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }

class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ['title', 'location', 'type', 'time', 'end_time', 'nights', 'notes', 'booking_reference', 'booking_via', 'booking_url', 'cost_booked', 'amount_paid', 'is_paid', 'cancellation_deadline', 'payment_method', 'distance_km', 'cost_estimated']
        widgets = {
            'cancellation_deadline': forms.DateInput(attrs={'type': 'date'}),
            'time': forms.TimeInput(attrs={'type': 'time', 'class': 'flatpickr-time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time', 'class': 'flatpickr-time'}),
        }


class DiaryEntryForm(forms.ModelForm):
    class Meta:
        model = DiaryEntry
        fields = ['text']
        widgets = {
            'text': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 5, 
                'placeholder': 'Was hast du heute erlebt?'
            }),
        }

class DiaryImageForm(forms.ModelForm):
    class Meta:
        model = DiaryImage
        fields = ['image', 'caption']

DiaryImageFormSet = inlineformset_factory(
    DiaryEntry, 
    DiaryImage, 
    form=DiaryImageForm,
    extra=1, 
    can_delete=True
)
