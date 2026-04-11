from django.urls import path
from .views import TripDashboardView, trip_create, trip_edit, event_create, event_edit, event_delete, event_inline_update, event_quick_add

app_name = 'travel'

urlpatterns = [
    path('', TripDashboardView.as_view(), name='dashboard'),
    path('trip/new/', trip_create, name='trip_create'),
    path('trip/<int:pk>/edit/', trip_edit, name='trip_edit'),
    path('day/<int:day_id>/event/new/', event_create, name='event_create'),
    path('event/<int:pk>/edit/', event_edit, name='event_edit'),
    path('event/<int:pk>/delete/', event_delete, name='event_delete'),
    path('event/<int:pk>/inline-update/', event_inline_update, name='event_inline_update'),
    path('day/<int:day_id>/quick-add/', event_quick_add, name='event_quick_add'),
]
