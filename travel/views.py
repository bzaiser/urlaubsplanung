from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView
from django.http import HttpResponse
from datetime import timedelta
from .models import Trip, Day
from .forms import TripForm

class TripDashboardView(ListView):
    model = Trip
    template_name = 'travel/dashboard.html'
    context_object_name = 'trips'

    def get_template_names(self):
        if self.request.htmx:
            return ['travel/partials/trip_list.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_trip'] = Trip.objects.first() # Simplification for now
        return context

def _generate_days(trip):
    """Utility to generate Day objects for the trip duration."""
    if not trip.start_date or not trip.end_date:
        return
    
    current_date = trip.start_date
    while current_date <= trip.end_date:
        Day.objects.get_or_create(
            trip=trip, 
            date=current_date, 
            defaults={'location': 'Planung läuft...'}
        )
        current_date += timedelta(days=1)

def trip_create(request):
    if request.method == 'POST':
        form = TripForm(request.POST)
        if form.is_valid():
            trip = form.save()
            _generate_days(trip)
            if request.htmx:
                return redirect('travel:dashboard')
            return redirect('travel:dashboard')
    else:
        form = TripForm()
    
    return render(request, 'travel/partials/trip_form.html', {'form': form})

def trip_edit(request, pk):
    trip = get_object_or_404(Trip, pk=pk)
    if request.method == 'POST':
        form = TripForm(request.POST, instance=trip)
        if form.is_valid():
            trip = form.save()
            _generate_days(trip) # Refresh days if dates changed
            return redirect('travel:dashboard')
    else:
        form = TripForm(instance=trip)
    
    return render(request, 'travel/partials/trip_form.html', {'form': form})
