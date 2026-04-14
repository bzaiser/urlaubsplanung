from django.urls import path
from .views import (
    TripDashboardView, trip_create, trip_edit, trip_delete,
    event_create, event_edit, event_delete, 
    event_inline_update, event_quick_add, 
    event_inline_create, day_bulk_edit, 
    day_inline_update, event_upload_voucher,
    event_bulk_delete, event_bulk_move,
    settings_modal, ai_wizard, template_create,
    template_edit, template_delete, ai_test_connection,
    trip_logic_check, global_expense_create, global_expense_edit, global_expense_delete,
    add_adjustment_food, expense_upload_voucher, export_trip_ics,
    event_type_picker
)

app_name = 'travel'

urlpatterns = [
    path('', TripDashboardView.as_view(), name='dashboard'),
    path('trip/new/', trip_create, name='trip_create'),
    path('trip/<int:pk>/edit/', trip_edit, name='trip_edit'),
    path('trip/<int:pk>/delete/', trip_delete, name='trip_delete'),
    path('day/<int:day_id>/event/new/', event_create, name='event_create'),
    path('day/<int:day_id>/event/type-picker/', event_type_picker, name='event_type_picker'),
    path('event/<int:pk>/edit/', event_edit, name='event_edit'),
    path('event/<int:pk>/delete/', event_delete, name='event_delete'),
    path('event/<int:pk>/inline-update/', event_inline_update, name='event_inline_update'),
    path('event/<int:pk>/upload-voucher/', event_upload_voucher, name='event_upload_voucher'),
    path('expense/<int:pk>/upload-voucher/', expense_upload_voucher, name='expense_upload_voucher'),
    path('day/<int:day_id>/quick-add/', event_quick_add, name='event_quick_add'),
    path('day/<int:day_id>/inline-create/', event_inline_create, name='event_inline_create'),
    path('day/<int:pk>/inline-update/', day_inline_update, name='day_inline_update'),
    path('event/bulk-delete/', event_bulk_delete, name='event_bulk_delete'),
    path('event/bulk-move/', event_bulk_move, name='event_bulk_move'),
    path('day/bulk-edit/', day_bulk_edit, name='day_bulk_edit'),
    
    # AI & Settings
    path('settings/', settings_modal, name='settings_modal'),
    path('ai/wizard/', ai_wizard, name='ai_wizard'),
    path('template/new/', template_create, name='template_create'),
    path('template/<int:pk>/edit/', template_edit, name='template_edit'),
    path('template/<int:pk>/delete/', template_delete, name='template_delete'),
    path('ai/test/', ai_test_connection, name='ai_test_connection'),
    
    # Logic & Global Expenses
    path('trip/<int:pk>/logic-check/', trip_logic_check, name='trip_logic_check'),
    path('trip/<int:trip_id>/expense/new/', global_expense_create, name='global_expense_create'),
    path('expense/<int:pk>/edit/', global_expense_edit, name='global_expense_edit'),
    path('expense/<int:pk>/delete/', global_expense_delete, name='global_expense_delete'),
    path('trip/<int:trip_id>/add-food-adjustment/', add_adjustment_food, name='add_adjustment_food'),
    path('trip/<int:pk>/export-ics/', export_trip_ics, name='export_trip_ics'),]
