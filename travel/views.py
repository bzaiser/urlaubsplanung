from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView
from django.http import HttpResponse
from datetime import timedelta
from .models import Trip, Day
from .forms import TripForm, EventForm

def _generate_days(trip):
    """Utility to generate Day objects for the trip duration."""
    if not trip.start_date or not trip.end_date:
        return
    
    current_date = trip.start_date
    while current_date <= trip.end_date:
        # get_or_create ensures we don't duplicate days or lose existing ones
        Day.objects.get_or_create(
            trip=trip, 
            date=current_date, 
            defaults={'location': 'Planung läuft...'}
        )
        current_date += timedelta(days=1)

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
        # Handle view type (timeline/table)
        view_type = self.request.GET.get('view', self.request.session.get('view_type', 'timeline'))
        self.request.session['view_type'] = view_type
        
        context['view_type'] = view_type
        context['active_trip'] = Trip.objects.first() 
        return context

def trip_create(request):
    if request.method == 'POST':
        form = TripForm(request.POST)
        if form.is_valid():
            trip = form.save()
            _generate_days(trip)
            if request.htmx:
                # Return the updated list to be swapped into the dashboard
                return render(request, 'travel/partials/trip_list.html', {'active_trip': trip})
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
            if request.htmx:
                return render(request, 'travel/partials/trip_list.html', {'active_trip': trip})
            return redirect('travel:dashboard')
    else:
        form = TripForm(instance=trip)
    
    return render(request, 'travel/partials/trip_form.html', {'form': form})

# Event Management Views
from .models import Event

def event_create(request, day_id):
    day = get_object_or_404(Day, pk=day_id)
    if request.method == 'POST':
        form = EventForm(request.POST, request.FILES)
        if form.is_valid():
            event = form.save(commit=False)
            event.day = day
            event.save()
            if request.htmx:
                return render(request, 'travel/partials/trip_list.html', {'active_trip': day.trip})
            return redirect('travel:dashboard')
    else:
        form = EventForm()
    
    return render(request, 'travel/partials/event_form.html', {
        'form': form,
        'day': day
    })

def event_edit(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if request.method == 'POST':
        form = EventForm(request.POST, request.FILES, instance=event)
        if form.is_valid():
            form.save()
            if request.htmx:
                return render(request, 'travel/partials/trip_list.html', {'active_trip': event.day.trip})
            return redirect('travel:dashboard')
    else:
        form = EventForm(instance=event)
    
    return render(request, 'travel/partials/event_form.html', {
        'form': form,
        'event': event,
        'day': event.day
    })

def event_delete(request, pk):
    event = get_object_or_404(Event, pk=pk)
    trip = event.day.trip
    if request.method == 'POST':
        event.delete()
        if request.htmx:
            return render(request, 'travel/partials/trip_list.html', {'active_trip': trip})
        return redirect('travel:dashboard')
    return HttpResponse(status=405)
