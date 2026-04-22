from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.contrib import messages
from django.views.generic import ListView
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect
from django.template.loader import render_to_string
from datetime import date, timedelta
from .models import (
    Trip, Day, Event, TripTemplate, GlobalSetting, GlobalExpense, 
    DiaryEntry, DiaryImage, ChecklistCategory, ChecklistTemplate, 
    ChecklistItemTemplate, TripChecklistItem, TripChecklist, TripVoucher
)
from .forms import TripForm, EventForm, DiaryEntryForm, DiaryImageFormSet
from django.template.defaultfilters import date as _date
from django.utils.translation import gettext_lazy as _
from django.db.models import Prefetch
from django.core.serializers.json import DjangoJSONEncoder
import json
from .services import ai_service, logic_service, checklist_service, geo_service
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.decorators.cache import never_cache
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)

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




def get_dashboard_context(request, active_trip=None):
    """Helper to prepare the full context for trip_list.html, 
    ensuring AG Grid and view types are always synchronized."""
    view_type = request.GET.get('view', request.session.get('view_type', 'timeline'))
    request.session['view_type'] = view_type
    
    show_map = request.GET.get('show_map') == '1'
    
    # Trip Selection logic (if not provided)
    if not active_trip:
        trip_id = request.GET.get('trip_id') or request.session.get('active_trip_id')
        if trip_id:
            active_trip = Trip.objects.filter(id=trip_id, user=request.user).prefetch_related(
                'days__diary__images', 'days__events'
            ).first()
            
            # Resilience: If ID was provided but trip not found, clear it from session
            if not active_trip:
                if 'active_trip_id' in request.session:
                    del request.session['active_trip_id']
                trip_id = None
            
        # Fallback to the latest trip for THIS user
        if not active_trip:
            active_trip = Trip.objects.filter(user=request.user).prefetch_related(
                'days__diary__images', 'days__events'
            ).order_by('-id').first()
            
    if active_trip:
        request.session['active_trip_id'] = active_trip.id
        if 'view_type' not in request.session:
            request.session['view_type'] = 'timeline'

    context = {
        'view_type': view_type,
        'active_trip': active_trip,
        'trips': Trip.objects.filter(user=request.user).order_by('name'),
    }
    
    # Checklist Context
    if active_trip and view_type == 'checklist':
        checklist = TripChecklist.objects.filter(trip=active_trip).first()
        context['checklist'] = checklist
        context['templates'] = ChecklistTemplate.objects.all()
        context['categories'] = ChecklistCategory.objects.all().prefetch_related(
            Prefetch('trip_items', 
                     queryset=TripChecklistItem.objects.filter(checklist=checklist),
                     to_attr='trip_items_list')
        )
        context['today'] = date.today()
    
    
    # 2. Prepare AG Grid Data (Only if needed for table view to save CPU)
    if active_trip and view_type == 'table':
        grid_data = []
        for i, station in enumerate(active_trip.grouped_stations):
            station_key = f"st-{i}"
            first_day = station['days'][0]
            grid_data.append({
                'id': f"station-{i}",
                'is_station_header': True,
                'station_key': station_key,
                'station_location': station['location'],
                'days_count': station['days_count'],
                'nights_count': station['nights_count'],
                'lat': float(first_day.latitude) if first_day.latitude else None,
                'lon': float(first_day.longitude) if first_day.longitude else None,
                'station_index': i
            })
            
            for day in station['days']:
                # Optimization: use Python sorting on prefetched queryset to avoid DB hits per day
                from datetime import time
                events = sorted(day.events.all(), key=lambda x: (x.time or time.min, x.id))
                acc_events = [e for e in events if e.type in ['HOTEL', 'CAMPING', 'PITCH', 'BUNGALOW']]
                
                acc_status = 'MISSING'
                acc_name = ''
                if acc_events:
                    main_acc = acc_events[0]
                    acc_name = main_acc.title or 'Unterkunft'
                    acc_status = 'FIX' if main_acc.cost_booked > 0 else 'PLANNED'
                
                grid_data.append({
                    'id': f"day-header-{day.id}",
                    'day_id': day.id,
                    'is_day_header': True,
                    'station_key': station_key,
                    'date_display': _date(day.date, "j. b"),
                    'day_name': _date(day.date, "D"),
                    'location': day.location,
                    'acc_status': acc_status,
                    'acc_name': acc_name,
                    'lat': float(day.latitude) if day.latitude else None,
                    'lon': float(day.longitude) if day.longitude else None,
                    'station_index': i
                })
                
                for event in events:
                    grid_data.append({
                        'id': event.id,
                        'day_id': day.id,
                        'station_key': station_key,
                        'type': event.type,
                        'title': event.title,
                        'location': event.location or day.location,
                        'lat': float(event.latitude) if event.latitude else (float(day.latitude) if day.latitude and not event.location else None),
                        'lon': float(event.longitude) if event.longitude else (float(day.longitude) if day.longitude and not event.location else None),
                        'dep_time': event.time.strftime('%H:%M') if event.time else '',
                        'arr_time': event.end_time.strftime('%H:%M') if event.end_time else '',
                        'duration': event.duration or '',
                        'distance_km': event.distance_km or '',
                        'cost_booked': float(event.cost_booked or 0),
                        'cost_estimated': float(event.cost_estimated or 0),
                        'amount_paid': float(event.amount_paid or 0),
                        'payment_method': event.get_payment_method_display() if event.payment_method != 'NONE' else '',
                        'cancellation_deadline': event.cancellation_deadline.strftime('%d.%m.') if event.cancellation_deadline else '',
                        'days_until_storno': (event.cancellation_deadline - date.today()).days if event.cancellation_deadline else None,
                        'cost_actual': float(event.cost_actual or 0),
                        'voucher_url': event.vouchers.first().file.url if event.vouchers.exists() else None,
                        'distance_km': event.distance_km,
                        'meals_info': event.meals_info,
                        'is_paid': event.is_paid,
                        'is_checkin': event.is_checkin,
                        'is_checkout': event.is_checkout,
                        'breakfast_included': event.breakfast_included,
                        'breakfast_cost': float(event.breakfast_cost or 0),
                        'notes': event.notes or '',
                        'lat': float(day.latitude) if day.latitude else None,
                        'lon': float(day.longitude) if day.longitude else None,
                        'station_index': i
                    })
            
        # Add Global Expenses at the very end
        grid_data.append({
            'id': 'global-header',
            'is_station_header': True,
            'station_location': 'PAUSCHALE POSTEN / BUDGET',
            'station_key': 'global',
            'days_count': '',
            'nights_count': ''
        })
        
        global_expenses = active_trip.global_expenses.all()
        for exp in global_expenses:
            grid_data.append({
                'id': f"global-{exp.id}",
                'is_global_expense': True,
                'station_key': 'global',
                'type': exp.expense_type,
                'title': exp.title,
                'location': 'Reiseweit',
                'unit_price': float(exp.unit_price or 0),
                'units': exp.units or 1,
                'cost_booked': float(exp.total_amount or 0),
                'cost_total': float(exp.total_amount or 0),
                'voucher_url': exp.vouchers.first().file.url if exp.vouchers.exists() else None,
                'cost_estimated': 0,
                'is_auto_calculated': exp.is_auto_calculated,
            })

        context['grid_data_json'] = json.dumps(grid_data, cls=DjangoJSONEncoder)
    
    if active_trip:
        context['ui_settings_json'] = json.dumps(active_trip.ui_settings or {})
    # 3. Prepare Map Data (Step-by-Step Transparency: Show everything with coords)
    map_data = []
    coords_for_routing = []
    geocoding_was_pending = False
    route_geometry = []
    processed_locations = []
    
    if active_trip:
        def get_transport_icon(type_code):
            icon_map = {
                'FLIGHT': '✈️', 'CAR': '🚗', 'RENTAL_CAR': '🚗', 'CAMPER': '🚐',
                'CAMPING': '⛺', 'PITCH': '🚐📍', 'BOAT': '🛥️', 'FERRY': '⛴️',
                'TRAIN': '🚆', 'METRO': '🚇', 'TRAM': '🚋', 'TAXI': '🚕', 'BUS': '🚌',
                'SCOOTER': '🛵', 'ACTIVITY': '🎒', 'RESTAURANT': '🍽️'
            }
            return icon_map.get(type_code, '🐦')

        # Collect EVERY coordinate found, in sequence (Day then Projects/Events)
        for d_idx, day in enumerate(active_trip.days.all().order_by('date'), 1):
            # Prefetch image and text context
            d_image = ""
            d_text = ""
            if hasattr(day, 'diary'):
                d_text = day.diary.text[:200]
                primary_img = day.diary.images.filter(is_primary=True).first() or day.diary.images.first()
                if primary_img:
                    d_image = primary_img.get_url

            # 0. Departure Point (if exists, e.g. "Oberstenfeld" in "Oberstenfeld - Toblacher See")
            origin, dest = geo_service.extract_route_parts(day.location)
            if day.departure_latitude and day.departure_longitude:
                map_data.append({
                    'location': origin or f"Start ({day.location})",
                    'lat': float(day.departure_latitude),
                    'lon': float(day.departure_longitude),
                    'day_id': day.id,
                    'index': f"{d_idx}.0",
                    'is_event': False,
                    'image_url': d_image,
                    'description': f"Start: {origin or day.location}",
                    'date_str': _date(day.date, "j. b Y"),
                    'transport_icon': '🛫' # Initial start icon
                })
                coords_for_routing.append([float(day.departure_longitude), float(day.departure_latitude)])

            # 1. Day Location (if exists, the destination)
            if day.latitude and day.longitude:
                # Check for transport event of the day
                trans_ev = day.events.filter(type__in=['FLIGHT', 'CAR', 'RENTAL_CAR', 'CAMPER', 'TRAIN', 'BUS', 'BOAT', 'FERRY']).first()
                
                map_data.append({
                    'location': dest or day.location,
                    'lat': float(day.latitude),
                    'lon': float(day.longitude),
                    'day_id': day.id,
                    'index': d_idx,
                    'is_event': False,
                    'image_url': d_image,
                    'description': d_text,
                    'date_str': _date(day.date, "j. b Y"),
                    'transport_icon': get_transport_icon(trans_ev.type if trans_ev else 'NONE')
                })
                coords_for_routing.append([float(day.longitude), float(day.latitude)])
                
            # 2. All Events for that day (if they have coordinates)
            for e_idx, ev in enumerate(day.events.all().order_by('time', 'id'), 1):
                if ev.latitude and ev.longitude:
                    map_data.append({
                        'location': ev.location,
                        'lat': float(ev.latitude),
                        'lon': float(ev.longitude),
                        'is_event': True,
                        'event_type': ev.type,
                        'title': ev.title,
                        'day_id': day.id,
                        'index': f"{d_idx}.{e_idx}",
                        'image_url': d_image,
                        'description': ev.title,
                        'date_str': _date(day.date, "j. b Y"),
                        'transport_icon': get_transport_icon(ev.type)
                    })
                    coords_for_routing.append([float(ev.longitude), float(ev.latitude)])
        
        context['map_data_json'] = json.dumps(map_data, cls=DjangoJSONEncoder)
        
        # Trigger background geocoding for missing items
        from .models import Event
        geocoding_was_pending = (
            active_trip.days.filter(is_geocoded=False).exclude(location='').exclude(location='Planung läuft...').exists() or
            Event.objects.filter(day__trip=active_trip, is_geocoded=False, type__in=['FLIGHT', 'TRAIN', 'FERRY', 'BUS', 'CAR']).exclude(location='').exists()
        )
        
        # Routing: Calculate whenever we have coordinates (even on full page load)
        if len(coords_for_routing) > 1:
            route_geometry = geo_service.get_route_geometry(coords_for_routing)

        # Silent Background Processing (HTMX only)
        if request.htmx and geocoding_was_pending:
            geocoding_was_pending, processed_locations = geo_service.update_trip_coordinates(active_trip, limit=10)
            
            # Deduplicate and clean for UI
            unique_locations = list(dict.fromkeys([loc for loc in processed_locations if loc and loc.strip()]))
            context['last_geocoded'] = ", ".join(unique_locations)
            
            # Re-calculate routing if new pins were just found in this refresh
            if len(coords_for_routing) > 1:
                route_geometry = geo_service.get_route_geometry(coords_for_routing)

    context['geocoding_pending'] = geocoding_was_pending
    context['route_geometry_json'] = json.dumps(route_geometry)
    context['last_geocoded_raw'] = processed_locations
    context['trip'] = active_trip

    return context

class TripDashboardView(LoginRequiredMixin, ListView):
    model = Trip
    template_name = 'travel/trip_dashboard.html'
    context_object_name = 'trips'

    def get_queryset(self):
        return Trip.objects.filter(user=self.request.user).order_by('name')

    def get_template_names(self):
        if self.request.htmx:
            # If map view is requested alone, return only the map partial
            if self.request.GET.get('view') == 'map':
                return ['travel/partials/trip_map.html']
            return ['travel/partials/trip_list.html']
        return [self.template_name]

    def render_to_response(self, context, **response_kwargs):
        active_trip = context.get('active_trip')
        view_type = context.get('view_type', 'timeline')
        
        # Server-side Cache for partials (Synology Performance Optimization)
        cache_key = None
        if active_trip and self.request.htmx:
            # We cache by trip ID, user ID and view type (so Bernd doesn't see Klaus's trip)
            cache_key = f"dashboard_partial_{active_trip.id}_{self.request.user.id}_{view_type}"
            cached_response = cache.get(cache_key)
            if cached_response:
                logger.info(f"⚡ Cache Hit: {cache_key}")
                return HttpResponse(cached_response)

        if self.request.htmx:
            # Render the primary partial (trip_list or trip_map)
            template_name = self.get_template_names()[0]
            primary_html = render_to_string(template_name, context, request=self.request)
            
            # Prepare OOB switcher
            switcher_html = render_to_string('travel/partials/trip_switcher.html', {
                'active_trip': active_trip,
                'view_type': view_type,
                'trips': context.get('trips'),
                'is_oob': True
            }, request=self.request)
            
            final_html = primary_html + "\n" + switcher_html
            
            if cache_key:
                # Cache for 10 minutes (invalidated by signals on change)
                cache.set(cache_key, final_html, 600)
                logger.info(f"💾 Cache Set: {cache_key}")
                
            return HttpResponse(final_html)
            
        return super().render_to_response(context, **response_kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Use centralized helper
        dashboard_context = get_dashboard_context(self.request)
        context.update(dashboard_context)
        return context

@login_required
def trip_create(request):
    if request.method == 'POST':
        form = TripForm(request.POST)
        if form.is_valid():
            trip = form.save(commit=False)
            trip.user = request.user
            trip.save()
            _generate_days(trip)
            # Set as active trip
            request.session['active_trip_id'] = trip.id
            # Full redirect to refresh navbar and switcher
            if request.htmx:
                response = HttpResponse("")
                response['HX-Redirect'] = f"/?trip_id={trip.id}"
                return response
            return redirect('travel:dashboard')
        else:
            print(f"DEBUG: Trip form errors: {form.errors.as_text()}")
    else:
        form = TripForm()
    
    return render(request, 'travel/partials/trip_form.html', {'form': form})

@login_required
def trip_edit(request, pk):
    trip = get_object_or_404(Trip, pk=pk, user=request.user)
    if request.method == 'POST':
        original_start_date = trip.start_date
        form = TripForm(request.POST, instance=trip)
        if form.is_valid():
            do_shift = request.POST.get('shift_dates') == 'on'
            
            if do_shift:
                new_start_date = form.cleaned_data['start_date']
                offset = (new_start_date - original_start_date).days
                if offset != 0:
                    from .services import logic_service
                    logic_service.shift_entire_trip(trip, offset)
                    # Shift logic already saved the trip and shifted everything
                    # Re-bind form to shifted trip to save other possible changes (name, persons_count, etc)
                    form = TripForm(request.POST, instance=trip)
                    if form.is_valid():
                        form.save()
                else:
                    form.save()
            else:
                trip = form.save()
                _generate_days(trip) # Refresh days if dates changed but no shift requested
            
            if request.htmx:
                response = HttpResponse("")
                response['HX-Refresh'] = 'true'
                return response
            return redirect('travel:dashboard')
    else:
        form = TripForm(instance=trip)
    
    return render(request, 'travel/partials/trip_form.html', {'form': form})

@login_required
def trip_delete(request, pk):
    trip = get_object_or_404(Trip, pk=pk, user=request.user)
    if request.method == 'DELETE' or request.method == 'POST':
        trip.delete()
        if request.session.get('active_trip_id') == pk:
            request.session['active_trip_id'] = None
        if request.htmx:
            # SAFETY RE-INITIALIZATION: Return a hard redirect to clear URL parameters
            # and prevent Service Worker cache conflicts with deleted IDs.
            from django.urls import reverse
            response = HttpResponse("")
            response['HX-Redirect'] = reverse('travel:dashboard')
            return response
        return redirect('travel:dashboard')
    
    # Return confirmation partial for GET
    return render(request, 'travel/partials/trip_delete_confirm.html', {'trip': trip})

# Event Management Views
from .models import Event

@login_required
def event_type_picker(request, day_id):
    """Shows a grid of event types to choose from before opening the form."""
    day = get_object_or_404(Day, pk=day_id)
    return render(request, 'travel/partials/event_type_picker.html', {'day': day})

@login_required
def event_create(request, day_id):
    day = get_object_or_404(Day, pk=day_id)
    if request.method == 'POST':
        form = EventForm(request.POST, request.FILES)
        if form.is_valid():
            event = form.save(commit=False)
            event.day = day
            event.save()
            
            # Handle new vouchers if uploaded via main form (multiple supported)
            vouchers = request.FILES.getlist('voucher')
            if vouchers:
                from .models import TripVoucher
                for f in vouchers:
                    TripVoucher.objects.create(event=event, file=f, original_filename=f.name)
            
            if request.htmx:
                response = HttpResponse("")
                response['HX-Refresh'] = 'true'
                return response
            return redirect('travel:dashboard')
        else:
            if request.htmx:
                response = render(request, 'travel/partials/event_form.html', {'form': form, 'day': day})
                response['HX-Retarget'] = '#modal-container'
                return response
    else:
        initial_type = request.GET.get('type', 'NONE')
        initial_data = {'type': initial_type}
        conflict_warning = None
        
        if initial_type == 'RENTAL_CAR':
            # 1. Suggest days based on station length
            future_days = Day.objects.filter(trip=day.trip, date__gte=day.date).order_by('date')
            count = 0
            for d in future_days:
                if d.location == day.location:
                    count += 1
                else:
                    break
            initial_data['nights'] = count
            
            # 2. Check for conflicts (Flights, Trains, etc. during these days)
            # We check the next 'count' days for other transport events
            if count > 0:
                end_date = day.date + timedelta(days=count)
                conflicts = Event.objects.filter(
                    day__trip=day.trip,
                    day__date__gt=day.date,
                    day__date__lte=end_date
                ).filter(
                    type__in=['FLIGHT', 'TRAIN', 'BUS', 'FERRY', 'RENTAL_CAR']
                ).select_related('day')
                
                if conflicts.exists():
                    c_types = ", ".join(list(set([c.get_type_display() for c in conflicts])))
                    conflict_warning = f"Achtung: Du hast in diesem Zeitraum bereits andere Buchungen ({c_types}). Sicher, dass die Mietdauer stimmt?"

        form = EventForm(initial=initial_data)
    
    return render(request, 'travel/partials/event_form.html', {
        'form': form,
        'day': day,
        'conflict_warning': conflict_warning if 'conflict_warning' in locals() else None
    })

@login_required
def event_edit(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if request.method == 'POST':
        form = EventForm(request.POST, request.FILES, instance=event)
        if form.is_valid():
            event = form.save()
            # Handle new vouchers if uploaded via main form (multiple supported)
            vouchers = request.FILES.getlist('voucher')
            if vouchers:
                from .models import TripVoucher
                for f in vouchers:
                    TripVoucher.objects.create(event=event, file=f, original_filename=f.name)
            
            if request.htmx:
                response = HttpResponse("")
                response['HX-Refresh'] = 'true'
                return response
            return redirect('travel:dashboard')
        else:
            if request.htmx:
                response = render(request, 'travel/partials/event_form.html', {
                    'form': form, 'event': event, 'day': event.day
                })
                response['HX-Retarget'] = '#modal-container'
                return response
    else:
        form = EventForm(instance=event)
    
    return render(request, 'travel/partials/event_form.html', {
        'form': form,
        'event': event,
        'day': event.day
    })

@login_required
def event_delete(request, pk):
    event = get_object_or_404(Event, pk=pk)
    trip = event.day.trip
    # AJAX delete support (vanilla fetch in grid)
    if (request.headers.get('X-Requested-With') == 'XMLHttpRequest') and not request.headers.get('HX-Request'):
        event.delete()
        return HttpResponse(status=204)
        
    if request.method == 'POST':
        event.delete()
        if request.htmx:
            response = HttpResponse("")
            response['HX-Refresh'] = 'true'
            return response
        return render(request, 'travel/partials/trip_list.html', get_dashboard_context(request, trip))
    return HttpResponse(status=405)

@login_required
def event_inline_create(request, day_id):
    """Creates a new event inline and returns the new full row to refresh IDs."""
    day = get_object_or_404(Day, pk=day_id)
    field = request.POST.get('field')
    value = request.POST.get('value')
    
    if not value or value.strip() == "":
        return HttpResponse("")
        
    type_choice = 'ACTIVITY'
    if field in ['hotel_title', 'cost_per_person', 'cost_total', 'meals_info'] or 'hotel' in field:
        type_choice = 'HOTEL'
    elif 'transport' in field or 'flight' in field or field in ['time', 'end_time']:
        type_choice = 'TRANSPORT'
        
    event = Event.objects.create(day=day, title="Planung", type=type_choice)
    
    if field and field != 'title' and field != 'hotel_title':
        if hasattr(event, field):
            setattr(event, field, value)
            event.save()
    elif field == 'title' or field == 'hotel_title':
        event.title = value
        event.save()
            
    # Calculate initial duration if times were provided
    # Return the full row
    return render(request, 'travel/partials/day_row.html', {'day': day})

@login_required
def event_inline_update(request, pk=None, day_id=None):
    """Updates or creates an event field. Returns 204 or OOB duration update."""
    field = request.POST.get('field')
    value = request.POST.get('value')
    event_type = request.POST.get('type')
    
    # Improved time/number cleaning for backend robustness
    if value == "":
        value = None
    
    if value and field in ['time', 'end_time']:
        value = str(value).strip().lower()
        if 'uhr' in value: value = value.replace('uhr', '').strip()
        if ':' not in value:
            if value.isdigit():
                if len(value) <= 2: value = f"{value.zfill(2)}:00"
                elif len(value) == 4: value = f"{value[:2]}:{value[2:]}"
        # Final validation/cleanup
        if ':' in value:
            parts = value.split(':')
            if len(parts) >= 2:
                value = f"{parts[0].zfill(2)}:{parts[1].zfill(2)}"[:5]
    
    if pk:
        event = get_object_or_404(Event, pk=pk)
    elif day_id:
        day = get_object_or_404(Day, pk=day_id)
        if not event_type:
            # Smart defaults based on field names
            if field in ['cost_booked', 'cost_estimated', 'cost_per_person', 'cost_total', 'is_paid']:
                event_type = 'ACTIVITY' # Default to activity for costs if unknown
            elif field in ['time', 'end_time', 'distance_km']:
                event_type = 'TRANSPORT'
            else:
                event_type = 'ACTIVITY'
        event, created = Event.objects.get_or_create(day=day, type=event_type, defaults={'title': 'Planung'})
    else:
        return HttpResponse(status=400)
    
    if field and hasattr(event, field):
        if field == 'is_paid':
            event.is_paid = (value == 'true')
        elif field == 'hotel_title':
            event.title = value
        elif field == 'location':
            event.location = value
            # Instant Geocoding for manual edits!
            from .services import geo_service
            if value:
                lat, lon = geo_service.geocode_location(value, event.day.trip)
                if lat and lon:
                    event.latitude = lat
                    event.longitude = lon
                    event.is_geocoded = True
            else:
                event.latitude = None
                event.longitude = None
                event.is_geocoded = False
        else:
            setattr(event, field, value)
        event.save()
        
        # If location changed, return the coordinates so the frontend can show the pin immediately
        if field == 'location':
            return JsonResponse({
                'status': 'success',
                'lat': float(event.latitude) if event.latitude else None,
                'lon': float(event.longitude) if event.longitude else None,
            })
        
    # Re-enable OOB duration update
    if field in ['time', 'end_time']:
        duration_val = event.duration or "--"
        oob_html = f'<td id="duration-{event.day.id}" hx-swap-oob="innerHTML">{duration_val}</td>'
        return HttpResponse(oob_html)
        
    return HttpResponse(status=204)



@login_required
def event_quick_add(request, day_id):
    """Quickly adds an activity/event just by title."""
    day = get_object_or_404(Day, pk=day_id)
    title = request.POST.get('title')
    if title:
        # Check if it's a hotel or flight based on keywords for smart defaults
        type_choice = 'NONE' # Default to neutral
        hotel_keywords = ['hotel', 'unterkunft', 'bungalow', 'camping', 'stellplatz', 'raststätte', 'zimmer', 'guesthouse']
        if any(kw in title.lower() for kw in hotel_keywords):
            type_choice = 'HOTEL'
        elif 'flug' in title.lower() or 'flight' in title.lower():
            type_choice = 'FLIGHT'
            
        Event.objects.create(day=day, title=title, type=type_choice)
        
    return render(request, 'travel/partials/trip_list.html', get_dashboard_context(request, day.trip))

@login_required
def day_bulk_edit(request):
    """Updates multiple days (location, station) at once. Triggers full refresh."""
    if request.method == 'POST':
        day_ids = request.POST.getlist('day_ids')
        location = request.POST.get('location')
        station = request.POST.get('station')
        
        if day_ids:
            updates = {}
            if location is not None:
                updates['location'] = location
            if station is not None:
                updates['station'] = station
                
            if updates:
                Day.objects.filter(id__in=day_ids).update(**updates)
                
            if request.htmx:
                response = HttpResponse("")
                response['HX-Refresh'] = 'true'
                return response
    return redirect('travel:dashboard')

@login_required
def day_insert(request):
    """Inserts an empty day at a specific position and shifts everything else."""
    if request.method == 'POST':
        day_id = request.POST.get('day_id')
        if not day_id:
            # Fallback to first selected if multiple
            day_id = request.POST.getlist('day_ids')[0] if request.POST.getlist('day_ids') else None
        
        if day_id:
            from .services import logic_service
            day = get_object_or_404(Day, pk=day_id)
            trip = day.trip
            insert_date = day.date
            
            # 1. Shift all days from this date onwards by 1
            logic_service.shift_days(trip, insert_date, 1)
            
            # 2. Create the new empty day at the original date
            Day.objects.create(trip=trip, date=insert_date, location=day.location)
            
            if request.htmx:
                response = HttpResponse("")
                response['HX-Refresh'] = 'true'
                return response
    return redirect('travel:dashboard')

@login_required
def day_delete_and_shift(request):
    """Deletes selected days and shifts subsequent days forward to close the gap."""
    if request.method == 'POST':
        day_ids = request.POST.getlist('day_ids')
        if day_ids:
            from .services import logic_service
            days = Day.objects.filter(id__in=day_ids).order_by('date')
            if days.exists():
                trip = days.first().trip
                first_deleted_date = days.first().date
                num_days = days.count()
                
                # Delete the days
                days.delete()
                
                # Shift subsequent days forward by -num_days
                logic_service.shift_days(trip, first_deleted_date, -num_days)
                
                if request.htmx:
                    response = HttpResponse("")
                    response['HX-Refresh'] = 'true'
                    return response
    return redirect('travel:dashboard')

@login_required
def trip_shift_dates(request, pk):
    """Shifts the entire trip by a given offset."""
    trip = get_object_or_404(Trip, pk=pk)
    if request.method == 'POST':
        offset = int(request.POST.get('offset', 0))
        if offset != 0:
            from .services import logic_service
            logic_service.shift_entire_trip(trip, offset)
            
        if request.htmx:
            response = HttpResponse("")
            response['HX-Refresh'] = 'true'
            return response
    return render(request, 'travel/partials/trip_shift_modal.html', {'trip': trip})

@login_required
@never_cache
def day_edit(request, pk):
    """Provides a modal for editing a single day's title/location."""
    day = get_object_or_404(Day, pk=pk)
    if request.method == 'POST':
        location = request.POST.get('location', '')
        lat = request.POST.get('latitude')
        lon = request.POST.get('longitude')
        
        day.location = location
        if lat and lon:
            try:
                day.latitude = float(lat.replace(',', '.'))
                day.longitude = float(lon.replace(',', '.'))
                day.is_geocoded = True
            except ValueError: pass
        
        day.save()
        if request.htmx:
            response = HttpResponse("")
            response['HX-Refresh'] = 'true'
            return response
        return redirect('travel:dashboard')
    
    return render(request, 'travel/partials/day_form.html', {'day': day})

@login_required
def day_inline_update(request, pk):
    """Updates the location of a day via HTMX (background sync)."""
    day = get_object_or_404(Day, pk=pk)
    location = request.POST.get('value', request.POST.get('location'))
    # Allow empty location
    if location is not None:
        day.location = location
        # Instant Geocoding for manual edits!
        from .services import geo_service
        if location:
            lat, lon = geo_service.geocode_location(location, day.trip)
            if lat and lon:
                day.latitude = lat
                day.longitude = lon
                day.is_geocoded = True
        else:
            day.latitude = None
            day.longitude = None
            day.is_geocoded = False
        day.save()
    
    # Return JSON for AG-Grid to capture new coordinates
    return JsonResponse({
        'status': 'success',
        'location': day.location,
        'lat': float(day.latitude) if day.latitude else None,
        'lon': float(day.longitude) if day.longitude else None,
    })

from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse

@csrf_exempt
@login_required
def event_upload_voucher(request, pk):
    """Directly uploads one or more files to an existing event via AJAX/HTMX."""
    if request.method == 'POST' and request.FILES.getlist('voucher'):
        from .models import TripVoucher
        event = get_object_or_404(Event, pk=pk)
        vouchers = request.FILES.getlist('voucher')
        last_url = ""
        for f in vouchers:
            voucher = TripVoucher.objects.create(
                event=event,
                file=f,
                original_filename=f.name
            )
            last_url = voucher.file.url
        return JsonResponse({'status': 'success', 'voucher_url': last_url})
    return JsonResponse({'status': 'error'}, status=400)

@login_required
def voucher_delete(request, pk):
    """Deletes a specific attachment."""
    from .models import TripVoucher
    voucher = get_object_or_404(TripVoucher, pk=pk)
    if request.method == 'POST':
        voucher.delete()
        if request.htmx:
            response = HttpResponse("")
            response['HX-Refresh'] = 'true'
            return response
    return HttpResponse(status=405)

@login_required
def event_bulk_delete(request):
    """Deletes multiple events selected in the grid."""
    if request.method == 'POST':
        event_ids = request.POST.getlist('event_ids')
        events = Event.objects.filter(id__in=event_ids)
        if events.exists():
            trip = events.first().day.trip
            events.delete()
            if request.htmx:
                response = HttpResponse("")
                response['HX-Refresh'] = 'true'
                return response
            return render(request, 'travel/partials/trip_list.html', {'active_trip': trip})
    return HttpResponse(status=405)

@login_required
def event_bulk_move(request):
    """Moves selected events to a new target date."""
    if request.method == 'POST':
        event_ids = request.POST.getlist('event_ids')
        target_date_str = request.POST.get('target_date')
        if not event_ids or not target_date_str:
            return HttpResponse(status=400)
            
        events = Event.objects.filter(id__in=event_ids)
        if events.exists():
            trip = events.first().day.trip
            from datetime import datetime
            try:
                target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
                target_day, _ = Day.objects.get_or_create(trip=trip, date=target_date, defaults={'location': 'Planung...'})
                
                # Update all events to the new day
                events.update(day=target_day)
                
                if request.htmx:
                    response = HttpResponse("")
                    response['HX-Refresh'] = 'true'
                    return response
                return render(request, 'travel/partials/trip_list.html', {'active_trip': trip})
            except ValueError:
                return HttpResponse("Ungültiges Datum", status=400)
    return HttpResponse(status=405)

# --- AI & SETTINGS VIEWS ---

def get_setting(key, default='', user=None):
    try:
        return GlobalSetting.objects.get(key=key, user=user).value
    except GlobalSetting.DoesNotExist:
        return default

@login_required
def settings_modal(request):
    """View to manage API Keys, Provider and Trip Templates."""
    templates = TripTemplate.objects.filter(user=request.user).order_by('-created_at')
    gemini_key = GlobalSetting.objects.filter(key='gemini_api_key', user=request.user).first()
    groq_key = GlobalSetting.objects.filter(key='groq_api_key', user=request.user).first()
    active_provider = GlobalSetting.objects.filter(key='active_ai_provider', user=request.user).first()
    ollama_model = get_setting('ollama_model_name', 'llama3', user=request.user)
    ollama_url = get_setting('ollama_url', 'http://192.168.123.107:11434', user=request.user)
    
    # Vehicle Profiles
    v1_name = get_setting('vehicle1_name', 'Wohnmobil', user=request.user)
    v1_consump = get_setting('vehicle1_consumption', '12', user=request.user)
    v1_fuel = get_setting('vehicle1_fuel_type', 'Diesel', user=request.user)
    v1_weight = get_setting('vehicle1_weight', '3.5t', user=request.user)
    v1_range = get_setting('vehicle1_range', '600', user=request.user)

    v2_name = get_setting('vehicle2_name', 'Privat-PKW', user=request.user)
    v2_consump = get_setting('vehicle2_consumption', '8', user=request.user)
    v2_fuel = get_setting('vehicle2_fuel_type', 'Benzin', user=request.user)
    v2_range = get_setting('vehicle2_range', '500', user=request.user)

    # Fuel Prices
    diesel_price = get_setting('diesel_price', '1.60', user=request.user)
    petrol_price = get_setting('petrol_price', '1.70', user=request.user)

    
    # User Profile & Participants
    home_city = get_setting('user_home_city', 'München', user=request.user)
    home_addr = get_setting('user_home_address', '', user=request.user)
    def_p_count = get_setting('default_persons_count', '2', user=request.user)
    def_p_ages = get_setting('default_persons_ages', '40, 38', user=request.user)

    # Food Budgets
    food_self_l = get_setting('food_self_low', '10')
    food_self_m = get_setting('food_self_med', '15')
    food_self_h = get_setting('food_self_high', '25')
    food_out_l = get_setting('food_out_low', '20')
    food_out_m = get_setting('food_out_med', '40')
    food_out_h = get_setting('food_out_high', '70')

    
    if request.method == 'POST':
        # Vehicles & Profile update
        for k in [
            'vehicle1_name', 'vehicle1_consumption', 'vehicle1_fuel_type', 'vehicle1_weight', 'vehicle1_range',
            'vehicle2_name', 'vehicle2_consumption', 'vehicle2_fuel_type', 'vehicle2_range',
            'user_home_city', 'user_home_address', 'default_persons_count', 'default_persons_ages',
            'diesel_price', 'petrol_price',
            'food_self_low', 'food_self_med', 'food_self_high',
            'food_out_low', 'food_out_med', 'food_out_high'
        ]:
            val = request.POST.get(k, '').strip()
            GlobalSetting.objects.update_or_create(key=k, user=request.user, defaults={'value': val})

        return render(request, 'travel/partials/settings_modal.html', {
            'templates': templates,
            'user_home_city': request.POST.get('user_home_city'),
            'user_home_address': request.POST.get('user_home_address'),
            'default_persons_count': request.POST.get('default_persons_count'),
            'default_persons_ages': request.POST.get('default_persons_ages'),
            'success': True
        })

    return render(request, 'travel/partials/settings_modal.html', {
        'templates': templates,
        'v1_name': v1_name, 'v1_consumption': v1_consump, 'v1_fuel': v1_fuel, 'v1_weight': v1_weight, 'v1_range': v1_range,
        'v2_name': v2_name, 'v2_consumption': v2_consump, 'v2_fuel': v2_fuel, 'v2_range': v2_range,
        'user_home_city': home_city, 'user_home_address': home_addr,
        'default_persons_count': def_p_count, 'default_persons_ages': def_p_ages,
        'diesel_price': diesel_price, 'petrol_price': petrol_price,
        'food_self_low': food_self_l, 'food_self_med': food_self_m, 'food_self_high': food_self_h,
        'food_out_low': food_out_l, 'food_out_med': food_out_m, 'food_out_high': food_out_h,
    })

@login_required
def template_create(request):
    """Simple view to create a new trip template."""
    if request.method == 'POST':
        name = request.POST.get('name')
        prefs = request.POST.get('preferences')
        if name and prefs:
            TripTemplate.objects.create(user=request.user, name=name, preferences=prefs)
            return settings_modal(request) # Return refreshed settings list
    return render(request, 'travel/partials/template_form.html')

@login_required
def template_edit(request, pk):
    """View to edit an existing trip template."""
    template = get_object_or_404(TripTemplate, pk=pk, user=request.user)
    if request.method == 'POST':
        template.name = request.POST.get('name')
        template.preferences = request.POST.get('preferences')
        template.save()
        return settings_modal(request)
    return render(request, 'travel/partials/template_form.html', {'template': template})

@login_required
def template_delete(request, pk):
    """View to delete a trip template."""
    template = get_object_or_404(TripTemplate, pk=pk)
    if request.method == 'POST':
        template.delete()
        return settings_modal(request)
    return HttpResponse(status=405)

from django.views.decorators.csrf import csrf_exempt

@login_required
def ai_wizard(request):
    """
    Step-by-step wizard for AI trip generation.
    Supports initial prompt and refinement instructions.
    """
    step = request.GET.get('step', 'select')
    templates = TripTemplate.objects.all()
    
    # Default context values
    context = {
        'step': step,
        'templates': templates,
        'days': request.POST.get('days', 28),
        'start_date': request.POST.get('start_date', ''),
        'start_location': request.POST.get('start_location', ''),
        'persons_count': request.POST.get('persons_count', 2),
        'persons_ages': request.POST.get('persons_ages', ''),
        'user_preferences': request.POST.get('user_preferences', ''),
        'template_id': request.POST.get('template_id', ''),
    }
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'manual_step':
            template_id = request.POST.get('template_id')
            days = request.POST.get('days', 28)
            start_date = request.POST.get('start_date')
            start_location = request.POST.get('start_location', '')
            persons_count = request.POST.get('persons_count', 2)
            persons_ages = request.POST.get('persons_ages', '')
            user_prefs = request.POST.get('user_preferences', '').strip()

            try:
                template = get_object_or_404(TripTemplate, pk=template_id, user=request.user)
                # Combine template + user wishes
                final_preferences = template.preferences
                if user_prefs:
                    final_preferences = f"Style: {template.preferences}. Specific Wishes/Destination: {user_prefs}."
                
                # Generate the prompt for the user to copy
                prompt = ai_service.get_itinerary_prompt(
                    final_preferences, start_date, days, start_location, persons_count, persons_ages,
                    user=request.user
                )
                
                context.update({
                    'step': 'manual',
                    'prompt': prompt,
                    'start_date': start_date,
                    'days': days,
                    'persons_count': persons_count,
                    'persons_ages': persons_ages,
                })
                return render(request, 'travel/partials/ai_wizard.html', context)
            except Exception as e:
                context.update({'step': 'error', 'error': f"Fehler bei der Prompt-Erstellung: {str(e)}"})
                return render(request, 'travel/partials/ai_wizard.html', context)

        elif action == 'manual_import':
            pasted_text = request.POST.get('pasted_text', '').strip()
            start_date = request.POST.get('start_date')
            persons_count = request.POST.get('persons_count', 2)
            persons_ages = request.POST.get('persons_ages', '')
            
            try:
                pasted_text = ai_service.repair_json(pasted_text)
                trip_data = json.loads(pasted_text)
                trip = ai_service.save_itinerary_to_db(trip_data, start_date, persons_count, persons_ages, user=request.user)
                
                request.session['active_trip_id'] = trip.id
                
                if request.htmx:
                    response = HttpResponse("")
                    response['HX-Redirect'] = f"/?trip_id={trip.id}"
                    return response
                return redirect('travel:dashboard')
            except Exception as e:
                context.update({'step': 'error', 'error': f"Fehler beim Einlesen: {str(e)}"})
                return render(request, 'travel/partials/ai_wizard.html', context)

            
        elif action == 'import':
            itinerary_json = request.POST.get('itinerary_json')
            start_date = request.POST.get('start_date')
            persons_count = request.POST.get('persons_count', 2)
            persons_ages = request.POST.get('persons_ages', '')
            user_trip_name = request.POST.get('trip_name')
            
            trip_data = json.loads(itinerary_json)
            if user_trip_name:
                trip_data['name'] = user_trip_name
                
            try:
                trip = ai_service.save_itinerary_to_db(trip_data, start_date, persons_count, persons_ages, user=request.user)
                request.session['active_trip_id'] = trip.id

                if request.htmx:
                    response = HttpResponse("")
                    response['HX-Redirect'] = f"/?trip_id={trip.id}"
                    return response
                return redirect('travel:dashboard')
            except Exception as e:
                context.update({'step': 'error', 'error': f"Fehler beim Speichern: {str(e)}"})
                return render(request, 'travel/partials/ai_wizard.html', context)

    if step == 'select':
        templates = TripTemplate.objects.filter(user=request.user).order_by('-created_at')
        home_city = get_setting('user_home_city', '', user=request.user)
        p_count = get_setting('default_persons_count', '2', user=request.user)
        p_ages = get_setting('default_persons_ages', '40, 38', user=request.user)
        
        return render(request, 'travel/partials/ai_wizard.html', {
            'step': 'select', 
            'templates': templates,
            'start_location': home_city,
            'persons_count': p_count,
            'persons_ages': p_ages
        })

    return render(request, 'travel/partials/ai_wizard.html', {
        'step': step
    })

# --- LOGIC & GLOBAL EXPENSE VIEWS ---

@login_required
def trip_logic_check(request, pk):
    """Runs consistency checks and returns the results modal."""
    trip = get_object_or_404(Trip, pk=pk, user=request.user)
    findings = logic_service.check_trip_logic(trip)
    return render(request, 'travel/partials/logic_check_modal.html', {
        'trip': trip,
        'findings': findings
    })

@login_required
def global_expense_create(request, trip_id):
    trip = get_object_or_404(Trip, pk=trip_id)
    if request.method == 'POST':
        title = request.POST.get('title')
        expense_type = request.POST.get('expense_type', 'OTHER')
        try:
            unit_price = float(request.POST.get('unit_price', 0).replace(',', '.'))
            units = int(request.POST.get('units', 1))
        except (ValueError, TypeError):
            unit_price = 0
            units = 1
            
        expense = GlobalExpense.objects.create(
            trip=trip, title=title, expense_type=expense_type,
            unit_price=unit_price, units=units
        )
        
        # Handle new vouchers if uploaded via main form (multiple supported)
        vouchers = request.FILES.getlist('voucher')
        if vouchers:
            from .models import TripVoucher
            for f in vouchers:
                TripVoucher.objects.create(expense=expense, file=f, original_filename=f.name)
        return HttpResponse(headers={'HX-Refresh': 'true'})
    return render(request, 'travel/partials/global_expense_form.html', {'trip': trip})

@login_required
def global_expense_edit(request, pk):
    expense = get_object_or_404(GlobalExpense, pk=pk)
    if request.method == 'POST':
        expense.title = request.POST.get('title')
        expense.expense_type = request.POST.get('expense_type', 'OTHER')
        try:
            expense.unit_price = float(request.POST.get('unit_price', 0).replace(',', '.'))
            expense.units = int(request.POST.get('units', 1))
        except (ValueError, TypeError):
            pass
        expense.save()
        
        # Handle new vouchers if uploaded via main form (multiple supported)
        vouchers = request.FILES.getlist('voucher')
        if vouchers:
            from .models import TripVoucher
            for f in vouchers:
                TripVoucher.objects.create(expense=expense, file=f, original_filename=f.name)
            
        return HttpResponse(headers={'HX-Refresh': 'true'})
    return render(request, 'travel/partials/global_expense_form.html', {'expense': expense, 'trip': expense.trip})

@login_required
def global_expense_delete(request, pk):
    expense = get_object_or_404(GlobalExpense, pk=pk)
    expense.delete()
    return HttpResponse(headers={'HX-Refresh': 'true'})


@login_required
def export_trip_ics(request, pk):
    """Generates an .ics file for the complete trip."""
    trip = get_object_or_404(Trip, pk=pk)
    
    lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//Urlaubsplaner//DE',
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
        f'X-WR-CALNAME:{trip.name}',
    ]
    
    from datetime import datetime, time
    
    for day in trip.days.all():
        for event in day.events.all():
            lines.append('BEGIN:VEVENT')
            lines.append(f'UID:event-{event.id}@urlaubsplaner.local')
            
            # Format: YYYYMMDDTHHMMSSZ
            start_dt = datetime.combine(day.date, event.time or time(9, 0))
            if event.end_time:
                end_dt = datetime.combine(day.date, event.end_time)
            else:
                end_dt = datetime.combine(day.date, event.time or time(10, 0))
                # Add 1 hour if no end time
                from datetime import timedelta
                if not event.end_time: end_dt += timedelta(hours=1)
            
            lines.append(f"DTSTAMP:{datetime.now().strftime('%Y%MT%H%M%S')}")
            lines.append(f"DTSTART:{start_dt.strftime('%Y%m%dT%H%M%S')}")
            lines.append(f"DTEND:{end_dt.strftime('%Y%m%dT%H%M%S')}")
            
            summary = f"{event.get_type_display()}: {event.title}"
            lines.append(f"SUMMARY:{summary}")
            
            desc = event.notes or ""
            if event.cost_booked > 0:
                desc += f" | Kosten: {event.cost_booked}€ (Bezahlt: {'Ja' if event.is_paid else 'Nein'})"
            
            lines.append(f"DESCRIPTION:{desc}")
            if event.location:
                lines.append(f"LOCATION:{event.location}")
            
            lines.append('END:VEVENT')
            
    lines.append('END:VCALENDAR')
    
    from django.utils.text import slugify
    filename = slugify(trip.name or f"trip_{trip.id}")
    ics_content = "\r\n".join(lines)
    response = HttpResponse(ics_content, content_type='text/calendar')
    response['Content-Disposition'] = f'attachment; filename="{filename}.ics"'
    return response

@login_required
def expense_upload_voucher(request, pk):
    """Directly uploads one or more files to an existing global expense via AJAX/HTMX."""
    if request.method == 'POST' and request.FILES.getlist('voucher'):
        from .models import TripVoucher
        expense = get_object_or_404(GlobalExpense, pk=pk)
        vouchers = request.FILES.getlist('voucher')
        last_url = ""
        for f in vouchers:
            voucher = TripVoucher.objects.create(
                expense=expense,
                file=f,
                original_filename=f.name
            )
            last_url = voucher.file.url
        return JsonResponse({'status': 'success', 'voucher_url': last_url})
    return JsonResponse({'status': 'error'}, status=400)

@login_required
def add_adjustment_food(request, trip_id):
    """Smart fix to add missing food budget."""
    trip = get_object_or_404(Trip, pk=trip_id)
    missing_count = int(request.POST.get('count', 0))
    if missing_count > 0:
        GlobalExpense.objects.create(
            trip=trip,
            title=f"Ausgleich: Verpflegung ({missing_count} Tage)",
            expense_type='FOOD',
            unit_price=50,
            units=missing_count,
            is_auto_calculated=True
        )
    return HttpResponse(headers={'HX-Refresh': 'true'})

@login_required
@never_cache
def edit_diary(request, day_id):
    day = get_object_or_404(Day, id=day_id)
    diary, created = DiaryEntry.objects.get_or_create(day=day)
    
    if request.method == 'POST':
        form = DiaryEntryForm(request.POST, instance=diary)
        formset = DiaryImageFormSet(request.POST, request.FILES, instance=diary)
        
        if form.is_valid():
            form.save()
            
            # Handle multiple file uploads
            files = request.FILES.getlist('images')
            for f in files:
                # Set as primary if no images exist yet
                is_first = not diary.images.exists()
                DiaryImage.objects.create(diary_entry=diary, image=f, is_primary=is_first)
            
            # Formset can still be used for caption updates of existing images
            formset = DiaryImageFormSet(request.POST, request.FILES, instance=diary)
            if formset.is_valid():
                formset.save()
            
            # Trigger refresh in timeline
            return HttpResponse(status=204, headers={'HX-Trigger': 'diaryUpdated'})
            
    else:
        form = DiaryEntryForm(instance=diary)
        formset = DiaryImageFormSet(instance=diary)
        
    context = {
        'day': day,
        'diary': diary,
        'form': form,
        'formset': formset,
    }
    return render(request, 'travel/partials/diary_modal.html', context)

@login_required
def delete_diary_image(request, image_id):
    image = get_object_or_404(DiaryImage, id=image_id)
    image.delete()
    return HttpResponse("") 

@login_required
def set_diary_image_primary(request, image_id):
    image = get_object_or_404(DiaryImage, id=image_id)
    diary = image.diary_entry
    
    # Unset other primary images for this diary
    diary.images.update(is_primary=False)
    
    # Set this one as primary
    image.is_primary = True
    image.save()
    
    # Return the updated modal to reflect state changes (yellow star)
    from .forms import DiaryEntryForm, DiaryImageFormSet
    form = DiaryEntryForm(instance=diary)
    formset = DiaryImageFormSet(instance=diary)
    context = {
        'day': diary.day,
        'diary': diary,
        'form': form,
        'formset': formset,
    }
    return render(request, 'travel/partials/diary_modal.html', context)

# --- Checklist Views ---

@login_required
def trip_checklist(request, trip_id):
    """Main view for a trip's checklist, grouped by category."""
    trip = get_object_or_404(Trip, pk=trip_id)
    view_type = request.GET.get('view', 'checklist') # Ensure view persists
    
    # Ensure checklist exists
    checklist, _ = TripChecklist.objects.get_or_create(trip=trip)
    
    # Items grouped by category
    categories = ChecklistCategory.objects.all().prefetch_related(
        Prefetch('trip_items', 
                 queryset=TripChecklistItem.objects.filter(checklist=checklist),
                 to_attr='trip_items_list')
    )
    
    templates = ChecklistTemplate.objects.all()
    
    context = {
        'trip': trip,
        'active_trip': trip,  # Added for template compatibility
        'checklist': checklist,
        'categories': categories,
        'templates': templates,
        'view_type': 'checklist',
        'today': date.today()
    }
    
    response_html = render_to_string('travel/partials/trip_checklist.html', context, request=request)
    
    if request.headers.get('HX-Request'):
        # Add switcher as OOB swap to keep navigation in sync
        switcher_html = render_to_string('travel/partials/trip_switcher.html', {
            'active_trip': trip,
            'view_type': 'checklist',
            'trips': Trip.objects.filter(user=request.user),
            'is_oob': True
        }, request=request)
        return HttpResponse(response_html + "\n" + switcher_html)
        
    return HttpResponse(response_html)

@login_required
@require_POST
def station_rename(request, trip_id):
    """
    Renames a station grouping (Day.station) for all days in a trip
    that currently share the old name.
    """
    trip = get_object_or_404(Trip, id=trip_id, user=request.user)
    old_name = request.POST.get('old_name')
    new_name = request.POST.get('new_name', '').strip()

    if old_name and new_name:
        # Update all days in this trip that match the old station name
        # 1. Matches where station was explicitly set
        Day.objects.filter(trip=trip, station=old_name).update(station=new_name)
        # 2. Matches where station was empty and location provided the name
        Day.objects.filter(trip=trip, station__in=["", None], location=old_name).update(station=new_name)

    # Re-render the dashboard (context includes grouped_stations)
    context = get_dashboard_context(request, active_trip=trip)
    return render(request, 'travel/partials/trip_list.html', context)

@login_required
@require_POST
def checklist_item_toggle(request, item_id):
    """HTMX view to toggle an item's completion status."""
    item = get_object_or_404(TripChecklistItem, pk=item_id)
    item.is_checked = not item.is_checked
    item.save()
    
    # Return nothing or a small status indicator if needed
    # But usually we re-render the checklist partial or just return 204
    return HttpResponse(status=204)

@login_required
def checklist_item_date_edit(request, item_id):
    """Returns an inline date input for editing a checklist item's due date."""
    item = get_object_or_404(TripChecklistItem, pk=item_id)
    # Render a simple date input that saves on change/blur
    html = f"""
    <input type="date" name="due_date" value="{item.due_date.isoformat() if item.due_date else ''}"
           class="form-control form-control-sm bg-dark text-warning border-warning"
           style="width: 130px; font-size: 0.75rem;"
           hx-post="{reverse('travel:checklist_item_date_save', args=[item.id])}"
           hx-trigger="blur, keyup[key=='Enter']"
           hx-swap="outerHTML"
           autoFocus>
    """
    return HttpResponse(html)

@login_required
def checklist_item_date_save(request, item_id):
    """Saves the updated date and returns the formatted badge."""
    item = get_object_or_404(TripChecklistItem, pk=item_id)
    new_date_str = request.POST.get('due_date')
    
    if new_date_str:
        try:
            from datetime import datetime
            item.due_date = datetime.strptime(new_date_str, '%Y-%m-%d').date()
            item.save()
        except (ValueError, TypeError):
            pass
    
    if not item.due_date:
        return HttpResponse("")
    
    # Return the updated badge
    from datetime import date
    today = date.today()
    badge_class = "bg-danger" if item.due_date < today else "bg-secondary text-opacity-75"
    
    display_date = item.due_date.strftime("%d. %m.")
    
    html = f"""
    <span class="badge rounded-pill {badge_class} small pointer" 
          style="font-size: 0.7rem; cursor: pointer;"
          hx-get="{reverse('travel:checklist_item_date_edit', args=[item.id])}"
          hx-swap="outerHTML"
          title="Datum ändern">
        <i class="bi bi-clock me-1"></i>{display_date}
    </span>
    """
    return HttpResponse(html)

@login_required
def checklist_apply_template(request, trip_id):
    """Action view to apply a template to a trip's checklist."""
    trip = get_object_or_404(Trip, pk=trip_id)
    template_id = request.POST.get('template_id')
    if template_id:
        template = get_object_or_404(ChecklistTemplate, pk=template_id)
        checklist_service.apply_template_to_trip(trip, template)
    
    return trip_checklist(request, trip_id)

@login_required
def checklist_reset(request, trip_id):
    """Deletes all items from a trip's checklist."""
    trip = get_object_or_404(Trip, pk=trip_id)
    if hasattr(trip, 'checklist'):
        trip.checklist.items.all().delete()
    
    return trip_checklist(request, trip_id)

@login_required
def checklist_item_add(request, trip_id):
    """HTMX Action to add a custom item."""
    trip = get_object_or_404(Trip, pk=trip_id)
    text = request.POST.get('text')
    category_id = request.POST.get('category_id')
    save_to_template = request.POST.get('save_to_template') == 'on'
    
    if text and category_id:
        checklist_service.add_custom_item(trip, text, category_id, save_to_template)
    
    return trip_checklist(request, trip_id)

@login_required
def checklist_template_modal(request, trip_id):
    """View to manage and bulk-save checklist template items (Vorgaben)."""
    trip = get_object_or_404(Trip, pk=trip_id)
    checklist = getattr(trip, 'checklist', None)
    
    if not checklist or not checklist.template:
        return HttpResponse("Keine Vorlage ausgewählt.")
        
    template = checklist.template
    # We only show and allow editing for "Vor der Abreise" items here
    items = template.items.filter(category__name="Vor der Abreise").order_by('text')
    
    if request.method == 'POST':
        for item in items:
            prefix = f"item_{item.id}_"
            new_text = request.POST.get(f"{prefix}text")
            new_days = request.POST.get(f"{prefix}days")
            
            if new_text is not None:
                item.text = new_text
            if new_days is not None:
                try:
                    item.due_days_before = int(new_days)
                except (ValueError, TypeError):
                    pass
            item.save()
            
        # Return success and trigger modal closing
        response = HttpResponse(status=204)
        response['HX-Trigger'] = 'closeModal'
        return response
    
    context = {
        'template': template,
        'items': items,
        'active_trip': trip
    }
    return render(request, 'travel/partials/checklist_template_modal.html', context)


@login_required
def checklist_template_manager(request, trip_id):
    """Returns a modal to manage (create/delete) global checklist templates."""
    trip = get_object_or_404(Trip, pk=trip_id, user=request.user)
    templates = ChecklistTemplate.objects.filter(user=request.user).order_by('name')
    
    context = {
        'templates': templates,
        'active_trip': trip
    }
    return render(request, 'travel/partials/checklist_template_manager_modal.html', context)

@login_required
def checklist_template_create_simple(request, trip_id):
    """Creates a new empty checklist template."""
    name = request.POST.get('name')
    if name:
        ChecklistTemplate.objects.create(name=name, user=request.user)
        
    # Return to the manager modal to show updated list
    return checklist_template_manager(request, trip_id)


@login_required
@never_cache
def checklist_template_delete_simple(request, trip_id, template_id):
    """Deletes a checklist template."""
    template = get_object_or_404(ChecklistTemplate, pk=template_id, user=request.user)
    template.delete()
    return checklist_template_manager(request, trip_id)

@login_required
def checklist_item_delete(request, item_id):
    """HTMX action to delete an item."""
    item = get_object_or_404(TripChecklistItem, pk=item_id)
    trip_id = item.checklist.trip_id
    item.delete()
    return trip_checklist(request, trip_id)

@login_required
def checklist_print(request, trip_id):
    """Print-friendly view of the trip checklist."""
    trip = get_object_or_404(Trip, pk=trip_id)
    checklist = getattr(trip, 'checklist', None)
    
    items_by_cat = {}
    if checklist:
        for item in checklist.items.all().order_by('category__order', 'text'):
            cat_name = item.category.name if item.category else "Sonstiges"
            if cat_name not in items_by_cat:
                items_by_cat[cat_name] = []
            items_by_cat[cat_name].append(item)
            
    show_status = request.GET.get('status') == '1'
            
    return render(request, 'travel/checklist_print.html', {
        'trip': trip,
        'items_by_cat': items_by_cat,
        'show_status': show_status
    })

from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
@login_required
def save_ui_settings(request, trip_id):
    if request.method == 'POST':
        trip = get_object_or_404(Trip, id=trip_id)
        try:
            data = json.loads(request.body)
            # Merge with existing settings
            current_settings = trip.ui_settings or {}
            current_settings.update(data)
            trip.ui_settings = current_settings
            trip.save()
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error', 'message': 'Only POST allowed'}, status=405)

@login_required
def force_geocode(request, trip_id):
    """Manually trigger geocoding for all missing or failed items in a trip (no batch limit)."""
    trip = get_object_or_404(Trip, id=trip_id)
    
    # Reset failed attempts so they can try again with the new logic
    from .models import Day, Event
    Day.objects.filter(trip=trip, is_geocoded=True, latitude__isnull=True).update(is_geocoded=False)
    Event.objects.filter(day__trip=trip, is_geocoded=True, latitude__isnull=True).update(is_geocoded=False)
    
    # Use a higher limit for manual force (e.g. 50 items)
    geo_service.update_trip_coordinates(trip, limit=50)
    return HttpResponseRedirect(f"{reverse('travel:dashboard')}?trip_id={trip.id}&view=map")


@login_required
def offline_diary_fallback(request):
    """Simple view to serve the offline fallback template for PWA caching."""
    return render(request, 'travel/partials/diary_offline_fallback.html')
@login_required
def fix_event_type(request, pk):
    """HTMX view to quickly fix an event type suggested by the Logic Check."""
    event = get_object_or_404(Event, pk=pk)
    new_type = request.POST.get('new_type')
    if new_type:
        event.type = new_type
        event.save()
    response = HttpResponse("")
    response['HX-Refresh'] = 'true'
    return response

@login_required
def import_polarsteps(request):
    """
    Handles the interactive Polarsteps import.
    GET: Returns the import modal.
    POST: Processes trip.json and returns mapping {step_id: diary_id}.
    """
    from .services.polarsteps_service import PolarstepsImporter
    
    if request.method == 'GET':
        return render(request, 'travel/partials/polarsteps_import_modal.html')
    
    # POST: Expects trip.json content
    try:
        raw_json = request.POST.get('json_data')
        if not raw_json:
            return JsonResponse({'status': 'error', 'message': 'Keine Daten empfangen.'}, status=400)
            
        json_str = ai_service.repair_json(raw_json)
        json_data = json.loads(json_str)
        
        importer = PolarstepsImporter()
        trip, steps_mapping = importer.create_trip_from_json(json_data, user=request.user)
        
        # Get list of already existing photo filenames for this trip
        existing_photos = list(DiaryImage.objects.filter(
            diary_entry__day__trip=trip
        ).values_list('image', flat=True))
        
        # We only need the basenames (e.g. ps_step_123_img.jpg)
        import os
        existing_filenames = [os.path.basename(f) for f in existing_photos]
        
        return JsonResponse({
            'status': 'success',
            'trip_id': trip.id,
            'mapping': steps_mapping,
            'existing_photos': existing_filenames
        })
    except Exception as e:
        import traceback
        logger.error(f"Polarsteps Import Error: {str(e)}\n{traceback.format_exc()}")
        return JsonResponse({'status': 'error', 'message': f'Fehler beim Einlesen: {str(e)}'}, status=400)

@login_required
def import_polarsteps_photo(request):
    """
    Handles sequential photo uploads for the Polarsteps import.
    Expects: diary_id, step_id, file.
    """
    from .services.polarsteps_service import PolarstepsImporter
    
    diary_id = request.POST.get('diary_id')
    step_id = request.POST.get('step_id')
    photo_file = request.FILES.get('file')
    filename = request.POST.get('filename')
    
    if not (diary_id and photo_file):
        return JsonResponse({'status': 'error', 'message': 'Missing data'}, status=400)
        
    try:
        importer = PolarstepsImporter()
        importer.save_photo(diary_id, photo_file, step_id, filename)
        return JsonResponse({'status': 'success'})
    except Exception as e:
        import traceback
        logger.error(f"Polarsteps Photo Error: {str(e)}\n{traceback.format_exc()}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@login_required
def sync_polarsteps_live(request, trip_id):
    from .services.polarsteps_service import PolarstepsImporter
    import re
    
    trip = get_object_or_404(Trip, id=trip_id, user=request.user)
    
    # Get URL from POST or from Trip model
    url = request.POST.get('polarsteps_url') or trip.polarsteps_url
    
    if not url:
        return JsonResponse({'status': 'error', 'message': _('Keine Polarsteps-URL hinterlegt.')}, status=400)

    # Save URL to trip if it's new
    if url != trip.polarsteps_url:
        trip.polarsteps_url = url
        trip.save()
        
    try:
        from .services.polarsteps_service import PolarstepsImporter
        PolarstepsImporter.sync_from_url(trip.polarsteps_url, user=request.user, existing_trip=trip)
        messages.success(request, _("Erfolgreich mit Polarsteps synchronisiert!"))
        return JsonResponse({'status': 'ok', 'redirect': reverse('travel:dashboard') + f'?trip_id={trip.id}'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def archive_polarsteps_images(request, trip_id):
    from .services.polarsteps_service import PolarstepsImporter
    
    trip = get_object_or_404(Trip, id=trip_id, user=request.user)
    
    try:
        # Show global loader
        count = PolarstepsImporter.archive_all_remote_images(trip)
        messages.success(request, _(f"{count} Bilder erfolgreich lokal archiviert!"))
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
@login_required
def bulk_photo_upload(request, trip_id):
    """
    Handles multiple photos uploaded via the 'Magic Match' feature.
    Matches photos to diary entries based on EXIF timestamps.
    """
    from .services.polarsteps_service import PolarstepsImporter
    trip = get_object_or_404(Trip, id=trip_id, user=request.user)
    
    if request.method == 'POST':
        files = request.FILES.getlist('files')
        results = {'success': 0, 'failed': 0, 'errors': []}
        
        for f in files:
            try:
                diary, status = PolarstepsImporter.match_photo_by_exif(trip, f)
                if diary and status == "success":
                    # Save photo with original sanitized name
                    DiaryImage.objects.create(
                        diary_entry=diary,
                        image=f,
                        caption=""  # Leave empty for cleaner UI as requested
                    )
                    results['success'] += 1
                else:
                    results['failed'] += 1
                    results['errors'].append(f"{f.name}: {status}")
            except Exception as e:
                results['failed'] += 1
                results['errors'].append(f"{f.name}: {str(e)}")
        
        return JsonResponse({'status': 'ok', 'results': results})
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)
