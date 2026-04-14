from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView
from django.http import HttpResponse, JsonResponse
from datetime import date, timedelta
from .models import Trip, Day, Event, TripTemplate, GlobalSetting, GlobalExpense
from .forms import TripForm, EventForm
from .services import ai_service, logic_service
import json

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

import json
from django.core.serializers.json import DjangoJSONEncoder


def get_dashboard_context(request, active_trip=None):
    """Helper to prepare the full context for trip_list.html, 
    ensuring AG Grid and view types are always synchronized."""
    view_type = request.GET.get('view', request.session.get('view_type', 'table'))
    request.session['view_type'] = view_type
    
    # Trip Selection logic (if not provided)
    if not active_trip:
        trip_id = request.GET.get('trip_id') or request.session.get('active_trip_id')
        if trip_id:
            active_trip = Trip.objects.filter(id=trip_id).first()
        else:
            active_trip = Trip.objects.first()
            
    if active_trip:
        request.session['active_trip_id'] = active_trip.id

    context = {
        'view_type': view_type,
        'active_trip': active_trip,
        'trips': Trip.objects.all().order_by('name'),
    }
    
    # Prepare AG Grid Data
    if active_trip:
        grid_data = []
        for i, station in enumerate(active_trip.grouped_stations):
            station_key = f"st-{i}"
            grid_data.append({
                'id': f"station-{i}",
                'is_station_header': True,
                'station_key': station_key,
                'station_location': station['location'],
                'days_count': station['days_count'],
                'nights_count': station['nights_count'],
            })
            
            for day in station['days']:
                events = day.events.all().order_by('time', 'id')
                acc_events = events.filter(type__in=['HOTEL', 'CAMPING', 'PITCH', 'BUNGALOW'])
                
                acc_status = 'MISSING'
                acc_name = ''
                if acc_events.exists():
                    main_acc = acc_events.first()
                    acc_name = main_acc.title or 'Unterkunft'
                    acc_status = 'FIX' if main_acc.cost_booked > 0 else 'PLANNED'
                
                grid_data.append({
                    'id': f"day-header-{day.id}",
                    'day_id': day.id,
                    'is_day_header': True,
                    'station_key': station_key,
                    'date_display': day.date.strftime('%d. %b'),
                    'day_name': day.date.strftime('%a'),
                    'location': day.location,
                    'acc_status': acc_status,
                    'acc_name': acc_name,
                })
                
                for event in events:
                    grid_data.append({
                        'id': event.id,
                        'day_id': day.id,
                        'station_key': station_key,
                        'type': event.type,
                        'title': event.title,
                        'location': event.location or day.location,
                        'dep_time': event.time.strftime('%H:%M') if event.time else '',
                        'arr_time': event.end_time.strftime('%H:%M') if event.end_time else '',
                        'duration': event.duration or '',
                        'distance_km': event.distance_km or '',
                        'cost_booked': float(event.cost_booked),
                        'cost_estimated': float(event.cost_estimated),
                        'amount_paid': float(event.amount_paid),
                        'payment_method': event.get_payment_method_display() if event.payment_method != 'NONE' else '',
                        'cancellation_deadline': event.cancellation_deadline.strftime('%d.%m.') if event.cancellation_deadline else '',
                        'days_until_storno': (event.cancellation_deadline - date.today()).days if event.cancellation_deadline else None,
                        'is_paid': event.is_paid,
                        'voucher_url': event.voucher.url if event.voucher else '',
                        'booking_url': event.booking_url,
                        'nights': event.nights,
                        'is_checkin': event.is_checkin,
                        'is_checkout': event.is_checkout,
                        'breakfast_included': event.breakfast_included,
                        'breakfast_cost': float(event.breakfast_cost),
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
                'type': exp.expense_type,
                'title': exp.title,
                'location': 'Reiseweit',
                'unit_price': float(exp.unit_price),
                'units': exp.units,
                'cost_booked': float(exp.total_amount),
                'cost_estimated': 0,
                'voucher_url': exp.voucher.url if exp.voucher else None,
                'is_auto_calculated': exp.is_auto_calculated,
            })

        context['grid_data_json'] = json.dumps(grid_data, cls=DjangoJSONEncoder)
        
    return context

class TripDashboardView(ListView):
    model = Trip
    template_name = 'travel/trip_dashboard.html'
    context_object_name = 'trips'

    def get_template_names(self):
        if self.request.htmx:
            return ['travel/partials/trip_list.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Use centralized helper
        dashboard_context = get_dashboard_context(self.request)
        context.update(dashboard_context)
        return context

def trip_create(request):
    if request.method == 'POST':
        form = TripForm(request.POST)
        if form.is_valid():
            trip = form.save()
            _generate_days(trip)
            # Set as active trip
            request.session['active_trip_id'] = trip.id
            # Full redirect to refresh navbar and switcher
            return redirect('travel:dashboard')
        else:
            print(f"DEBUG: Trip form errors: {form.errors.as_text()}")
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
                response = HttpResponse("")
                response['HX-Refresh'] = 'true'
                return response
            return redirect('travel:dashboard')
    else:
        form = TripForm(instance=trip)
    
    return render(request, 'travel/partials/trip_form.html', {'form': form})

def trip_delete(request, pk):
    trip = get_object_or_404(Trip, pk=pk)
    if request.method == 'DELETE' or request.method == 'POST':
        trip.delete()
        if request.session.get('active_trip_id') == pk:
            request.session['active_trip_id'] = None
        if request.htmx:
            # We return both the trip list and the switcher (OOB)
            context = get_dashboard_context(request)
            html = render(request, 'travel/partials/trip_list.html', context).content.decode('utf-8')
            html += render(request, 'travel/partials/trip_switcher.html', context).content.decode('utf-8')
            return HttpResponse(html)
        return redirect('travel:dashboard')
    return HttpResponse(status=405)

# Event Management Views
from .models import Event

def event_type_picker(request, day_id):
    """Shows a grid of event types to choose from before opening the form."""
    day = get_object_or_404(Day, pk=day_id)
    return render(request, 'travel/partials/event_type_picker.html', {'day': day})

def event_create(request, day_id):
    day = get_object_or_404(Day, pk=day_id)
    if request.method == 'POST':
        form = EventForm(request.POST, request.FILES)
        if form.is_valid():
            event = form.save(commit=False)
            event.day = day
            event.save()
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

def event_edit(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if request.method == 'POST':
        form = EventForm(request.POST, request.FILES, instance=event)
        if form.is_valid():
            form.save()
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
        else:
            setattr(event, field, value)
        event.save()
        
    # Re-enable OOB duration update
    if field in ['time', 'end_time']:
        duration_val = event.duration or "--"
        oob_html = f'<td id="duration-{event.day.id}" hx-swap-oob="innerHTML">{duration_val}</td>'
        return HttpResponse(oob_html)
        
    return HttpResponse(status=204)



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

def day_bulk_edit(request):
    """Updates multiple days (location, hotel) at once. Triggers full refresh."""
    if request.method == 'POST':
        day_ids = request.POST.getlist('day_ids')
        location = request.POST.get('location')
        if day_ids:
            Day.objects.filter(id__in=day_ids).update(location=location)
            if request.htmx:
                response = HttpResponse("")
                response['HX-Refresh'] = 'true'
                return response
    return redirect('travel:dashboard')
def day_inline_update(request, pk):
    """Updates the location of a day via HTMX."""
    day = get_object_or_404(Day, pk=pk)
    location = request.POST.get('value', request.POST.get('location'))
    # Allow empty location
    day.location = location if location is not None else day.location
    day.save()
    return HttpResponse(day.location)

from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse

@csrf_exempt
def event_upload_voucher(request, pk):
    """Directly uploads a file to an existing event via AJAX/HTMX."""
    if request.method == 'POST' and request.FILES.get('voucher'):
        event = get_object_or_404(Event, pk=pk)
        event.voucher = request.FILES['voucher']
        event.save()
        return JsonResponse({'status': 'success', 'voucher_url': event.voucher.url})
    return JsonResponse({'status': 'error'}, status=400)

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

def get_setting(key, default=''):
    try:
        return GlobalSetting.objects.get(key=key).value
    except GlobalSetting.DoesNotExist:
        return default

def settings_modal(request):
    """View to manage API Keys, Provider and Trip Templates."""
    templates = TripTemplate.objects.all().order_by('-created_at')
    gemini_key = GlobalSetting.objects.filter(key='gemini_api_key').first()
    groq_key = GlobalSetting.objects.filter(key='groq_api_key').first()
    active_provider = GlobalSetting.objects.filter(key='active_ai_provider').first()
    ollama_model = get_setting('ollama_model_name', 'llama3')
    ollama_url = get_setting('ollama_url', 'http://192.168.123.107:11434')
    
    # Vehicle Profiles
    v1_name = get_setting('vehicle1_name', 'Wohnmobil')
    v1_consump = get_setting('vehicle1_consumption', '12')
    v1_fuel = get_setting('vehicle1_fuel_type', 'Diesel')
    v1_weight = get_setting('vehicle1_weight', '3.5t')
    v1_range = get_setting('vehicle1_range', '600')

    v2_name = get_setting('vehicle2_name', 'Privat-PKW')
    v2_consump = get_setting('vehicle2_consumption', '8')
    v2_fuel = get_setting('vehicle2_fuel_type', 'Benzin')
    v2_range = get_setting('vehicle2_range', '500')

    # Fuel Prices
    diesel_price = get_setting('diesel_price', '1.60')
    petrol_price = get_setting('petrol_price', '1.70')

    
    # User Profile & Participants
    home_city = get_setting('user_home_city', 'München')
    home_addr = get_setting('user_home_address', '')
    def_p_count = get_setting('default_persons_count', '2')
    def_p_ages = get_setting('default_persons_ages', '40, 38')

    # Food Budgets
    food_self_l = get_setting('food_self_low', '10')
    food_self_m = get_setting('food_self_med', '15')
    food_self_h = get_setting('food_self_high', '25')
    food_out_l = get_setting('food_out_low', '20')
    food_out_m = get_setting('food_out_med', '40')
    food_out_h = get_setting('food_out_high', '70')

    
    if request.method == 'POST':
        # Handle Provider/Keys/Vehicles update
        if 'active_ai_provider' in request.POST:
            provider = request.POST.get('active_ai_provider', 'gemini')
            gemini_val = request.POST.get('gemini_api_key', '').strip()
            groq_val = request.POST.get('groq_api_key', '').strip()
            
            GlobalSetting.objects.update_or_create(key='active_ai_provider', defaults={'value': provider or 'gemini'})
            GlobalSetting.objects.update_or_create(key='gemini_api_key', defaults={'value': gemini_val or ''})
            GlobalSetting.objects.update_or_create(key='groq_api_key', defaults={'value': groq_val or ''})
            # Vehicles & Profile
            for k in [
                'vehicle1_name', 'vehicle1_consumption', 'vehicle1_fuel_type', 'vehicle1_weight', 'vehicle1_range',
                'vehicle2_name', 'vehicle2_consumption', 'vehicle2_fuel_type', 'vehicle2_range',
                'user_home_city', 'user_home_address', 'default_persons_count', 'default_persons_ages',
                'ollama_model_name', 'ollama_url', 'diesel_price', 'petrol_price',
                'food_self_low', 'food_self_med', 'food_self_high',
                'food_out_low', 'food_out_med', 'food_out_high'
            ]:
                val = request.POST.get(k, '').strip()
                GlobalSetting.objects.update_or_create(key=k, defaults={'value': val})


            
            return render(request, 'travel/partials/settings_modal.html', {
                'templates': templates,
                'gemini_key': gemini_val,
                'groq_key': groq_val,
                'active_provider': provider,
                'v1_name': request.POST.get('v1_name'),
                'v1_consumption': request.POST.get('v1_consumption'),
                'v1_fuel': request.POST.get('v1_fuel'),
                'v1_weight': request.POST.get('v1_weight'),
                'v1_range': request.POST.get('v1_range'),
                'v2_name': request.POST.get('v2_name'),
                'v2_consumption': request.POST.get('v2_consumption'),
                'v2_fuel': request.POST.get('v2_fuel'),
                'v2_range': request.POST.get('v2_range'),

                'user_home_city': request.POST.get('user_home_city'),
                'user_home_address': request.POST.get('user_home_address'),
                'default_persons_count': request.POST.get('default_persons_count'),
                'default_persons_ages': request.POST.get('default_persons_ages'),
                'ollama_model_name': request.POST.get('ollama_model_name'),
                'ollama_url': request.POST.get('ollama_url'),
                'success': True
            })


    return render(request, 'travel/partials/settings_modal.html', {
        'templates': templates,
        'gemini_key': gemini_key.value if gemini_key else '',
        'groq_key': groq_key.value if groq_key else '',
        'active_provider': active_provider.value if active_provider else 'gemini',
        'v1_name': v1_name, 'v1_consumption': v1_consump, 'v1_fuel': v1_fuel, 'v1_weight': v1_weight, 'v1_range': v1_range,
        'v2_name': v2_name, 'v2_consumption': v2_consump, 'v2_fuel': v2_fuel, 'v2_range': v2_range,
        'user_home_city': home_city, 'user_home_address': home_addr,

        'default_persons_count': def_p_count, 'default_persons_ages': def_p_ages,
        'ollama_model_name': ollama_model, 'ollama_url': ollama_url,
        'diesel_price': diesel_price, 'petrol_price': petrol_price,
        'food_self_low': food_self_l, 'food_self_med': food_self_m, 'food_self_high': food_self_h,
        'food_out_low': food_out_l, 'food_out_med': food_out_m, 'food_out_high': food_out_h,
    })


def ai_test_connection(request):
    """Diagnostic view using the new lightweight test function."""
    result = ai_service.test_ai_connection()
    
    if "error" in result:
        return HttpResponse(f"<span style='color: #e74c3c;'>❌ Fehler: {result['error']}</span>")
    
    msg = result.get('message', 'Unbekannte Antwort')
    return HttpResponse(f"<span style='color: #2ecc71;'>✅ KI sagt: {msg}</span>")

def template_create(request):
    """Simple view to create a new trip template."""
    if request.method == 'POST':
        name = request.POST.get('name')
        prefs = request.POST.get('preferences')
        if name and prefs:
            TripTemplate.objects.create(name=name, preferences=prefs)
            return settings_modal(request) # Return refreshed settings list
    return render(request, 'travel/partials/template_form.html')

def template_edit(request, pk):
    """View to edit an existing trip template."""
    template = get_object_or_404(TripTemplate, pk=pk)
    if request.method == 'POST':
        template.name = request.POST.get('name')
        template.preferences = request.POST.get('preferences')
        template.save()
        return settings_modal(request)
    return render(request, 'travel/partials/template_form.html', {'template': template})

def template_delete(request, pk):
    """View to delete a trip template."""
    template = get_object_or_404(TripTemplate, pk=pk)
    if request.method == 'POST':
        template.delete()
        return settings_modal(request)
    return HttpResponse(status=405)

from django.views.decorators.csrf import csrf_exempt

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
        'start_location': request.POST.get('start_location', 'Zuhause'),
        'persons_count': request.POST.get('persons_count', 2),
        'persons_ages': request.POST.get('persons_ages', ''),
        'user_preferences': request.POST.get('user_preferences', ''),
        'template_id': request.POST.get('template_id', ''),
    }
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'generate':
            template_id = request.POST.get('template_id')
            days = request.POST.get('days', 28)
            start_date = request.POST.get('start_date')
            
            if not start_date:
                context.update({'step': 'select', 'error': 'Bitte wähle ein Startdatum aus!'})
                return render(request, 'travel/partials/ai_wizard.html', context)

            start_location = request.POST.get('start_location', 'Zuhause')
            persons_count = request.POST.get('persons_count', 2)
            persons_ages = request.POST.get('persons_ages', '')
            
            try:
                template = get_object_or_404(TripTemplate, pk=template_id)
                user_prefs = request.POST.get('user_preferences', '').strip()
                
                # Combine template + user wishes
                final_preferences = template.preferences
                if user_prefs:
                    final_preferences = f"Style: {template.preferences}. Specific Wishes/Destination: {user_prefs}. (Note: Prioritize specific wishes over style if they conflict)."
                
                result = ai_service.generate_itinerary(final_preferences, start_date, days, start_location, persons_count, persons_ages)
                
                if "error" in result:
                    msg = result['error']
                    if "429" in msg or "Too Many Requests" in msg:
                        msg = "Die KI-Anbieter brauchen gerade eine kurze Pause (Anfrage-Limit). Bitte warte ca. 60 Sekunden und versuche es erneut."
                    context.update({'step': 'error', 'error': msg})
                    return render(request, 'travel/partials/ai_wizard.html', context)
                
                # Normalize for consistent template rendering
                context.update({
                    'step': 'preview', 
                    'itinerary': result,
                    'itinerary_json': json.dumps(result),
                })
                return render(request, 'travel/partials/ai_wizard.html', context)
            except Exception as e:
                import traceback
                error_detail = f"CRITICAL CRASH: {str(e)}\n{traceback.format_exc()}"
                context.update({'step': 'error', 'error': error_detail})
                return render(request, 'travel/partials/ai_wizard.html', context)

        elif action == 'manual_import':
            pasted_text = request.POST.get('pasted_text', '').strip()
            start_date = request.POST.get('start_date')
            persons_count = request.POST.get('persons_count', 2)
            persons_ages = request.POST.get('persons_ages', '')
            
            try:
                # Use the new repair_json utility to handle malformed/truncated output
                pasted_text = ai_service.repair_json(pasted_text)
                
                trip_data = json.loads(pasted_text)
                trip = ai_service.save_itinerary_to_db(trip_data, start_date, persons_count, persons_ages)
                
                # Set as active trip
                request.session['active_trip_id'] = trip.id
                
                # Redirect to dashboard without old GET parameters to ensure new trip is loaded
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
                trip = ai_service.save_itinerary_to_db(trip_data, start_date, persons_count, persons_ages)
                
                # Set as active trip
                request.session['active_trip_id'] = trip.id

                if request.htmx:
                    response = HttpResponse("")
                    response['HX-Redirect'] = f"/?trip_id={trip.id}"
                    return response
                return redirect('travel:dashboard')
            except Exception as e:
                context.update({'step': 'error', 'error': f"Fehler beim Speichern: {str(e)}"})
                return render(request, 'travel/partials/ai_wizard.html', context)
            
        elif action == 'refine':
            instructions = request.POST.get('instructions')
            itinerary_json = request.POST.get('itinerary_json')
            
            current_itinerary = json.loads(itinerary_json)
            result = ai_service.refine_itinerary(current_itinerary, instructions)
            
            if "error" in result:
                msg = result['error']
                if "429" in msg or "Too Many Requests" in msg:
                    msg = "Die KI-Anbieter brauchen gerade eine kurze Pause (Anfrage-Limit). Bitte warte ca. 60 Sekunden und versuche es erneut."
                context.update({'step': 'error', 'error': msg})
                return render(request, 'travel/partials/ai_wizard.html', context)
            
            # Normalize for consistent template rendering
            result = ai_service.normalize_itinerary(result)
                
            context.update({
                'step': 'preview', 
                'itinerary': result,
                'itinerary_json': json.dumps(result),
                'refined': True
            })

    if step == 'select':
        templates = TripTemplate.objects.all().order_by('-created_at')
        home_city = get_setting('user_home_city', 'München')
        p_count = get_setting('default_persons_count', '2')
        p_ages = get_setting('default_persons_ages', '40, 38')
        
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

def trip_logic_check(request, pk):
    """Runs consistency checks and returns the results modal."""
    trip = get_object_or_404(Trip, pk=pk)
    findings = logic_service.check_trip_logic(trip)
    return render(request, 'travel/partials/logic_check_modal.html', {
        'trip': trip,
        'findings': findings
    })

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
            
        GlobalExpense.objects.create(
            trip=trip, title=title, expense_type=expense_type,
            unit_price=unit_price, units=units
        )
        return HttpResponse(headers={'HX-Refresh': 'true'})
    return render(request, 'travel/partials/global_expense_form.html', {'trip': trip})

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
        return HttpResponse(headers={'HX-Refresh': 'true'})
    return render(request, 'travel/partials/global_expense_form.html', {'expense': expense, 'trip': expense.trip})

def global_expense_delete(request, pk):
    expense = get_object_or_404(GlobalExpense, pk=pk)
    expense.delete()
    return HttpResponse(headers={'HX-Refresh': 'true'})


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
    
    ics_content = "\r\n".join(lines)
    response = HttpResponse(ics_content, content_type='text/calendar')
    response['Content-Disposition'] = f'attachment; filename="trip_{trip.id}.ics"'
    return response

def expense_upload_voucher(request, pk):
    """Directly uploads a file to an existing global expense via AJAX/HTMX."""
    if request.method == 'POST' and request.FILES.get('voucher'):
        expense = get_object_or_404(GlobalExpense, pk=pk)
        expense.voucher = request.FILES['voucher']
        expense.save()
        return JsonResponse({'status': 'success', 'voucher_url': expense.voucher.url})
    return JsonResponse({'status': 'error'}, status=400)

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
