from datetime import date, timedelta
from ..models import Trip, Day, Event, GlobalExpense
from django.db.models import Q

def check_trip_logic(trip):
    """Runs all consistency checks and returns a list of findings."""
    findings = []
    
    findings.extend(check_accommodation_gaps(trip))
    findings.extend(check_transport_gaps(trip))
    findings.extend(check_meal_coverage(trip))
    findings.extend(check_vouchers(trip))
    findings.extend(check_storno_deadlines(trip))
    findings.extend(check_time_anomalies(trip))
    findings.extend(check_checkout_links(trip))
    findings.extend(check_checklist_deadlines(trip))
    
    return findings

def check_checklist_deadlines(trip):
    findings = []
    today = date.today()
    
    if hasattr(trip, 'checklist'):
        overdue = trip.checklist.items.filter(is_checked=False, due_date__lt=today)
        for item in overdue:
            findings.append({
                'id': 'CH_OVERDUE',
                'level': 'warning',
                'message': f"Checkliste: '{item.text}' ist seit {item.due_date.strftime('%d.%m.')} überfällig!",
                'fix_type': 'VIEW_CHECKLIST'
            })
    return findings

def check_accommodation_gaps(trip):
    findings = []
    days = trip.days.all().order_by('date')
    if not days:
        return []

    covered_dates = set()
    stay_types = ['HOTEL', 'CAMPING', 'PITCH', 'BUNGALOW']
    
    # Collect all covered dates
    all_events = Event.objects.filter(day__trip=trip, type__in=stay_types)
    for event in all_events:
        # A stay covers the night if it's not a pure checkout
        if not event.is_checkout:
            duration = event.nights or 1
            for i in range(duration):
                covered_dates.add(event.day.date + timedelta(days=i))

    for day in days:
        # The last day of the trip usually doesn't need a stay (Departure)
        if day.date != trip.end_date:
            if day.date not in covered_dates:
                findings.append({
                    'id': 'AC_GAP',
                    'level': 'error',
                    'day_id': day.id,
                    'date': day.date,
                    'message': f"Lücke in der Unterkunft am {day.date.strftime('%d.%m.')} ({day.location}).",
                    'fix_type': 'ADD_STAY'
                })
    return findings

def check_transport_gaps(trip):
    findings = []
    days = list(trip.days.all().order_by('date'))
    
    for i in range(len(days) - 1):
        current_day = days[i]
        next_day = days[i+1]
        
        if current_day.location != next_day.location:
            # Check if there is a transport event on either day
            transports = Event.objects.filter(
                Q(day=current_day) | Q(day=next_day),
                type__in=['FLIGHT', 'TRANSPORT', 'CAR', 'BOAT', 'FERRY', 'TAXI', 'BUS', 'TRAIN']
            )
            if not transports.exists():
                findings.append({
                    'id': 'TR_GAP',
                    'level': 'warning',
                    'day_id': next_day.id,
                    'date': next_day.date,
                    'message': f"Ortswechsel von {current_day.location} nach {next_day.location} ohne Transportmittel.",
                    'fix_type': 'ADD_TRANSPORT'
                })
    return findings

def check_meal_coverage(trip):
    findings = []
    days = trip.days.all().order_by('date')
    
    # Check if a global food expense exists
    has_global_food = trip.global_expenses.filter(expense_type='FOOD').exists()
    
    missing_days = []
    for day in days:
        # A day has meal coverage if:
        # 1. There is a RESTAURANT event
        # 2. There is a HOTEL event with breakfast_included
        # 3. meals_info is not empty (manual text)
        events = day.events.all()
        has_restaurant = events.filter(type='RESTAURANT').exists()
        has_breakfast = events.filter(type__in=['HOTEL', 'CAMPING', 'PITCH', 'BUNGALOW'], breakfast_included=True).exists()
        has_info = events.exclude(meals_info='').exists() or any(e.meals_info for e in events) # simplified
        
        if not (has_restaurant or has_breakfast or has_info):
            missing_days.append(day)
            
    if missing_days and not has_global_food:
        findings.append({
            'id': 'ME_GAP',
            'level': 'info',
            'count': len(missing_days),
            'message': f"An {len(missing_days)} Tagen ist keine Verpflegung (Restaurant/Frühstück) geplant.",
            'fix_type': 'ADD_FOOD_PAUSCHAL',
            'missing_day_ids': [d.id for d in missing_days]
        })
    return findings

def check_vouchers(trip):
    findings = []
    events = Event.objects.filter(day__trip=trip, cost_booked__gt=50, voucher='')
    for event in events:
        findings.append({
            'id': 'VO_MISSING',
            'level': 'warning',
            'event_id': event.id,
            'message': f"Beleg fehlt für '{event.title}' ({event.cost_booked}€).",
            'fix_type': 'UPLOAD_VOUCHER'
        })
    return findings

def check_storno_deadlines(trip):
    findings = []
    today = date.today()
    in_3_days = today + timedelta(days=3)
    
    events = Event.objects.filter(
        day__trip=trip, 
        cancellation_deadline__isnull=False,
        is_paid=False
    )
    
    for event in events:
        if event.cancellation_deadline < today:
            findings.append({
                'id': 'ST_EXPIRED',
                'level': 'error',
                'event_id': event.id,
                'message': f"Stornofrist für '{event.title}' abgelaufen ({event.cancellation_deadline.strftime('%d.%m.')})!",
            })
        elif event.cancellation_deadline <= in_3_days:
            findings.append({
                'id': 'ST_URGENT',
                'level': 'warning',
                'event_id': event.id,
                'message': f"Stornofrist für '{event.title}' läuft bald ab: {event.cancellation_deadline.strftime('%d.%m.')}.",
            })
    return findings

def check_time_anomalies(trip):
    findings = []
    events = Event.objects.filter(day__trip=trip, time__isnull=False, end_time__isnull=False)
    for event in events:
        if event.end_time < event.time:
            # Check if it's a known overnight thing (though duration property handles it, logic check should flag it if not expected)
            findings.append({
                'id': 'TI_ANOMALY',
                'level': 'warning',
                'event_id': event.id,
                'message': f"Endzeit ({event.end_time.strftime('%H:%M')}) liegt vor Startzeit ({event.time.strftime('%H:%M')}) bei '{event.title}'.",
            })
    return findings

def check_checkout_links(trip):
    findings = []
    # Find check-ins without a linked_checkout
    events = Event.objects.filter(day__trip=trip, type__in=['HOTEL', 'CAMPING', 'PITCH', 'BUNGALOW'])
    for event in events:
        if 'check-in' in event.title.lower() and not event.linked_checkout:
            findings.append({
                'id': 'CO_MISSING',
                'level': 'warning',
                'event_id': event.id,
                'message': f"Check-in '{event.title}' hat keinen verknüpften Check-out.",
                'fix_type': 'GENERATE_CHECKOUT'
            })
    return findings
