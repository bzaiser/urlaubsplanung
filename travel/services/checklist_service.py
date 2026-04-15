from datetime import timedelta, date
from travel.models import (
    ChecklistTemplate, ChecklistItemTemplate, 
    TripChecklist, TripChecklistItem, ChecklistCategory
)
from django.db import transaction

def apply_template_to_trip(trip, template):
    """
    Creates a TripChecklist for the trip based on the given template.
    Calculates due dates for each item.
    """
    with transaction.atomic():
        # Ensure only one checklist per trip
        checklist, created = TripChecklist.objects.get_or_create(
            trip=trip,
            defaults={'template': template}
        )
        
        # If it already existed and we are applying a NEW template, 
        # normally we should either merge or clear. 
        # For simplicity, we clear and re-apply if it's a new template assignment.
        if not created and checklist.template != template:
            checklist.items.all().delete()
            checklist.template = template
            checklist.save()

        # Copy items
        for item_template in template.items.all():
            due_date = None
            if trip.start_date and item_template.due_days_before > 0:
                due_date = trip.start_date - timedelta(days=item_template.due_days_before)
            
            TripChecklistItem.objects.create(
                checklist=checklist,
                category=item_template.category,
                text=item_template.text,
                due_date=due_date,
                is_template_item=True
            )
    return checklist

def add_custom_item(trip, text, category_id, save_to_template=False):
    """Adds a custom item to a trip's checklist."""
    checklist = getattr(trip, 'checklist', None)
    if not checklist:
        checklist = TripChecklist.objects.create(trip=trip)
    
    category = ChecklistCategory.objects.get(id=category_id)
    
    # Calculate due date if possible (default 0 days before)
    due_date = None # Custom items default to the trip start or today
    
    item = TripChecklistItem.objects.create(
        checklist=checklist,
        category=category,
        text=text,
        due_date=due_date,
        is_template_item=False
    )
    
    # If user wants to "Save back to template"
    if save_to_template and checklist.template:
        ChecklistItemTemplate.objects.get_or_create(
            template=checklist.template,
            category=category,
            text=text,
            defaults={'due_days_before': 0}
        )
    
    return item

def get_overdue_items(trip):
    """Returns checklist items that are overdue and not checked."""
    if not hasattr(trip, 'checklist'):
        return []
    
    today = date.today()
    return trip.checklist.items.filter(
        is_checked=False,
        due_date__lt=today
    )
