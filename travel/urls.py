from django.urls import path
from .views import TripDashboardView

app_name = 'travel'

urlpatterns = [
    path('', TripDashboardView.as_view(), name='dashboard'),
]
