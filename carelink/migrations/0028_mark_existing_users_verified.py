from django.db import migrations

def mark_existing_users_verified(apps, schema_editor):
    User = apps.get_model('carelink', 'User')
    User.objects.all().update(email_verified=True)

class Migration(migrations.Migration):
    dependencies = [
        ('carelink', '0027_mark_existing_users_verified'),
    ]

    operations = [
        migrations.RunPython(mark_existing_users_verified),
    ] 