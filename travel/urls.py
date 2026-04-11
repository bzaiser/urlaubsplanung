from django.urls import path
from .views import TripDashboardView, trip_create, trip_edit

app_name = 'travel'

urlpatterns = [
    path('', TripDashboardView.as_view(), name='dashboard'),
    path('trip/new/', trip_create, name='trip_create'),
    path('trip/<int:pk>/edit/', trip_edit, name='trip_edit'),
]
