from django.shortcuts import render
from django.views.generic import ListView
from .models import Trip

class TripDashboardView(ListView):
    model = Trip
    template_name = 'travel/dashboard.html'
    context_object_name = 'trips'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # For now, just a placeholder or the first trip
        context['active_trip'] = Trip.objects.first()
        return context
