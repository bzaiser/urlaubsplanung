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

def event_inline_update(request, pk):
    """Updates a single field of an event via HTMX. Returns only the field value to avoid full page refresh."""
    event = get_object_or_404(Event, pk=pk)
    field = request.POST.get('field')
    value = request.POST.get('value')
    
    if hasattr(event, field):
        setattr(event, field, value)
        event.save()
        
    return HttpResponse(getattr(event, field))

def event_inline_create(request, day_id):
    """Creates a new event inline from a table cell. Returns only the value to avoid full refresh."""
    day = get_object_or_404(Day, pk=day_id)
    field = request.POST.get('field')
    value = request.POST.get('value')
    
    if not value or value.strip() == "":
        return HttpResponse("")
        
    type_choice = 'ACTIVITY'
    if 'hotel' in field:
        type_choice = 'HOTEL'
    elif 'transport' in field or 'flight' in field:
        type_choice = 'TRANSPORT'
        
    event = Event.objects.create(day=day, title=value, type=type_choice)
    # Since we created it, the table cell needs to know the ID for future updates
    # For now, we return the value, but a full refresh might be cleaner on first creation
    # Let's return the whole list for the FIRST creation to get the IDs right
    return render(request, 'travel/partials/trip_list.html', {'active_trip': day.trip})

def event_quick_add(request, day_id):
    """Quickly adds an activity/event just by title."""
    day = get_object_or_404(Day, pk=day_id)
    title = request.POST.get('title')
    if title:
        # Check if it's a hotel or flight based on keywords for smart defaults
        type_choice = 'ACTIVITY'
        hotel_keywords = ['hotel', 'unterkunft', 'bungalow', 'camping', 'stellplatz', 'raststätte', 'zimmer', 'guesthouse']
        if any(kw in title.lower() for kw in hotel_keywords):
            type_choice = 'HOTEL'
        elif 'flug' in title.lower() or 'flight' in title.lower():
            type_choice = 'FLIGHT'
            
        Event.objects.create(day=day, title=title, type=type_choice)
        
    return render(request, 'travel/partials/trip_list.html', {'active_trip': day.trip})
