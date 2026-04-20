from django.db import migrations

def assign_trips_to_admin(apps, schema_editor):
    Trip = apps.get_model('travel', 'Trip')
    User = apps.get_model('auth', 'User')
    
    # Try to find the first superuser
    admin = User.objects.filter(is_superuser=True).first()
    
    # If no superuser, take any user
    if not admin:
        admin = User.objects.first()
        
    if admin:
        # Assign all trips that don't have a user yet
        Trip.objects.filter(user__isnull=True).update(user=admin)

class Migration(migrations.Migration):

    dependencies = [
        ('travel', '0026_trip_user'),
    ]

    operations = [
        migrations.RunPython(assign_trips_to_admin),
    ]
