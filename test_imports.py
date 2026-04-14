import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'urlaubsplanung.settings')
django.setup()
from travel.views import ai_wizard
print("Import success")
