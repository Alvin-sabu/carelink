# Generated by Django 5.1.7 on 2025-03-15 13:21

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('carelink', '0013_medicationreminder'),
    ]

    operations = [
        migrations.CreateModel(
            name='VitalSigns',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('recorded_at', models.DateTimeField(auto_now_add=True)),
                ('blood_pressure_systolic', models.IntegerField()),
                ('blood_pressure_diastolic', models.IntegerField()),
                ('heart_rate', models.IntegerField()),
                ('temperature', models.DecimalField(decimal_places=1, max_digits=4)),
                ('oxygen_saturation', models.IntegerField()),
                ('notes', models.TextField(blank=True, null=True)),
                ('patient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='carelink.patient')),
            ],
            options={
                'verbose_name': 'Vital Signs',
                'verbose_name_plural': 'Vital Signs',
                'ordering': ['-recorded_at'],
            },
        ),
    ]
