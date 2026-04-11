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
    """Updates a single field of an event via HTMX. Returns only the field value."""
    event = get_object_or_404(Event, pk=pk)
    field = request.POST.get('field')
    value = request.POST.get('value')
    
    if hasattr(event, field):
        # Handle numeric fields if necessary (but DecimalField handles strings okay in save)
        setattr(event, field, value)
        event.save()
        
    # Return formatted value for specific fields
    saved_val = getattr(event, field)
    if 'cost' in field:
        return HttpResponse(f"{saved_val:.2f}")
    return HttpResponse(saved_val)

def event_inline_create(request, day_id):
    """Creates a new event inline from a table cell. Returns only the value to avoid full refresh."""
    day = get_object_or_404(Day, pk=day_id)
    field = request.POST.get('field')
    value = request.POST.get('value')
    
    if not value or value.strip() == "":
        return HttpResponse("")
        
    type_choice = 'ACTIVITY'
    if field in ['hotel_title', 'cost_per_person', 'cost_total'] or 'hotel' in field:
        type_choice = 'HOTEL'
    elif 'transport' in field or 'flight' in field or field in ['time', 'end_time']:
        type_choice = 'TRANSPORT'
        
    event = Event.objects.create(day=day, title="Planung", type=type_choice)
    
    # If the user specifically set a field other than title, update it
    if field and field != 'title' and field != 'hotel_title':
        if hasattr(event, field):
            setattr(event, field, value)
            event.save()
    elif field == 'title' or field == 'hotel_title':
        event.title = value
        event.save()
            
    return render(request, 'travel/partials/trip_list.html', {'active_trip': day.trip, 'view_type': 'table'})


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

def day_bulk_edit(request):
    """Updates multiple days (location, hotel) at once. Returns full list to refresh stations."""
    if request.method == 'POST':
        day_ids = request.POST.getlist('day_ids')
        location = request.POST.get('location')
        hotel_title = request.POST.get('hotel_title')
        # Preserve view type
        view_type = request.GET.get('view', 'table')
        
        days = Day.objects.filter(id__in=day_ids)
        if location:
            days.update(location=location)
        
        if hotel_title:
            for day in days:
                # Update existing hotel or create new one
                hotel = day.events.filter(type='HOTEL').first()
                if hotel:
                    hotel.title = hotel_title
                    hotel.save()
                else:
                    Event.objects.create(day=day, title=hotel_title, type='HOTEL')
        
        if days.exists():
            return render(request, 'travel/partials/trip_list.html', {
                'active_trip': days.first().trip,
                'view_type': view_type
            })
            
    return HttpResponse(status=400)
def day_inline_update(request, pk):
    """Updates the location of a day via HTMX."""
    day = get_object_or_404(Day, pk=pk)
    location = request.POST.get('location')
    if location:
        day.location = location
        day.save()
    return HttpResponse(day.location)
