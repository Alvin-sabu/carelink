# Generated by Django 5.1.4 on 2025-03-22 14:44

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('carelink', '0025_remove_user_is_active_user_email_verified'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
    ]
