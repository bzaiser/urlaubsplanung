from django import forms
from .models import Trip, Event, Day, DiaryEntry, DiaryImage
from .services.ai_service import strip_duration_from_name
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

    def clean_name(self):
        name = self.cleaned_data.get('name')
        return strip_duration_from_name(name)

class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ['title', 'location', 'type', 'time', 'end_time', 'nights', 'latitude', 'longitude', 'notes', 'booking_reference', 'booking_via', 'booking_url', 'cost_booked', 'amount_paid', 'is_paid', 'cancellation_deadline', 'payment_method', 'distance_km', 'cost_estimated', 'breakfast_included', 'breakfast_cost']
        widgets = {
            'cancellation_deadline': forms.DateInput(attrs={'type': 'date'}),
            'time': forms.TimeInput(attrs={'type': 'time', 'class': 'flatpickr-time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time', 'class': 'flatpickr-time'}),
            'breakfast_included': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'breakfast_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
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
