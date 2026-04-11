from django.urls import path
from .views import TripDashboardView, trip_create, trip_edit

app_name = 'travel'

urlpatterns = [
    path('', TripDashboardView.as_view(), name='dashboard'),
    path('trip/new/', trip_create, name='trip_create'),
    path('trip/<int:pk>/edit/', trip_edit, name='trip_edit'),
    path('day/<int:day_id>/event/new/', event_create, name='event_create'),
    path('event/<int:pk>/edit/', event_edit, name='event_edit'),
    path('event/<int:pk>/delete/', event_delete, name='event_delete'),
]
