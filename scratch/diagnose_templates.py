import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from travel.models import ChecklistTemplate, ChecklistItemTemplate

templates = ChecklistTemplate.objects.all()
print(f"Gefundene Vorlagen: {len(templates)}")

for t in templates:
    items = t.items.all()
    print(f"\nVorlage: {t.name} (ID: {t.id})")
    print(f"Anzahl Einträge: {len(items)}")
    for item in items[:5]: # Zeige nur die ersten 5
        print(f"  - {item.text} (Kat: {item.category.name if item.category else 'None'})")
    if len(items) > 5:
        print("  ...")
