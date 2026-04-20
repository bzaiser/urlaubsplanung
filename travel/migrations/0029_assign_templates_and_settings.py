from django.db import migrations

def assign_templates_and_settings_to_admin(apps, schema_editor):
    TripTemplate = apps.get_model('travel', 'TripTemplate')
    ChecklistTemplate = apps.get_model('travel', 'ChecklistTemplate')
    GlobalSetting = apps.get_model('travel', 'GlobalSetting')
    User = apps.get_model('auth', 'User')
    
    admin = User.objects.filter(is_superuser=True).first()
    if not admin:
        admin = User.objects.first()
        
    if admin:
        TripTemplate.objects.filter(user__isnull=True).update(user=admin)
        ChecklistTemplate.objects.filter(user__isnull=True).update(user=admin)
        GlobalSetting.objects.filter(user__isnull=True).update(user=admin)

class Migration(migrations.Migration):

    dependencies = [
        ('travel', '0028_alter_globalsetting_options_checklisttemplate_user_and_more'),
    ]

    operations = [
        migrations.RunPython(assign_templates_and_settings_to_admin),
    ]
