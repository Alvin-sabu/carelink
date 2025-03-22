# Generated by Django 5.1.7 on 2025-03-15 13:39

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('carelink', '0014_vitalsigns'),
    ]

    operations = [
        migrations.CreateModel(
            name='MedicationAdherence',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('scheduled_time', models.DateTimeField()),
                ('taken_time', models.DateTimeField(blank=True, null=True)),
                ('status', models.CharField(choices=[('TAKEN', 'Taken'), ('MISSED', 'Missed'), ('SKIPPED', 'Skipped'), ('RESCHEDULED', 'Rescheduled')], max_length=20)),
                ('reason_if_missed', models.TextField(blank=True, null=True)),
                ('notes', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('medication', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='adherence_records', to='carelink.medication')),
            ],
            options={
                'ordering': ['-scheduled_time'],
            },
        ),
        migrations.CreateModel(
            name='MedicationInteraction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('severity', models.CharField(choices=[('MINOR', 'Minor'), ('MODERATE', 'Moderate'), ('MAJOR', 'Major'), ('SEVERE', 'Severe')], max_length=10)),
                ('description', models.TextField()),
                ('recommendations', models.TextField()),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('medication1', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='interactions_as_med1', to='carelink.medication')),
                ('medication2', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='interactions_as_med2', to='carelink.medication')),
            ],
            options={
                'ordering': ['-severity', '-created_at'],
                'unique_together': {('medication1', 'medication2')},
            },
        ),
        migrations.CreateModel(
            name='MedicationInventory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('current_quantity', models.IntegerField(default=0)),
                ('unit_of_measure', models.CharField(max_length=50)),
                ('reorder_point', models.IntegerField(help_text='Quantity at which to reorder')),
                ('last_refill_date', models.DateField(blank=True, null=True)),
                ('next_refill_date', models.DateField(blank=True, null=True)),
                ('auto_refill_enabled', models.BooleanField(default=False)),
                ('preferred_pharmacy', models.CharField(blank=True, max_length=200, null=True)),
                ('pharmacy_phone', models.CharField(blank=True, max_length=20, null=True)),
                ('prescription_insurance', models.CharField(blank=True, max_length=200, null=True)),
                ('insurance_group_number', models.CharField(blank=True, max_length=50, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('medication', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='inventory', to='carelink.medication')),
            ],
        ),
        migrations.CreateModel(
            name='MedicationSideEffect',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('symptom', models.CharField(max_length=200)),
                ('severity', models.CharField(choices=[('MILD', 'Mild'), ('MODERATE', 'Moderate'), ('SEVERE', 'Severe')], max_length=10)),
                ('description', models.TextField()),
                ('onset_time', models.CharField(help_text='Expected time for side effect to appear', max_length=100)),
                ('duration', models.CharField(help_text='Expected duration of the side effect', max_length=100)),
                ('action_required', models.TextField(help_text='Actions to take if this side effect occurs')),
                ('is_common', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('medication', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='side_effects', to='carelink.medication')),
            ],
            options={
                'ordering': ['-severity', 'symptom'],
            },
        ),
        migrations.RemoveField(
            model_name='exerciselog',
            name='patient',
        ),
        migrations.RemoveField(
            model_name='meallog',
            name='patient',
        ),
        migrations.RemoveField(
            model_name='mentalhealthlog',
            name='patient',
        ),
        migrations.RemoveField(
            model_name='nutritionplan',
            name='patient',
        ),
        migrations.RemoveField(
            model_name='supportgroup',
            name='facilitator',
        ),
        migrations.RemoveField(
            model_name='supportgroup',
            name='members',
        ),
        migrations.RemoveField(
            model_name='vitalsigns',
            name='patient',
        ),
        migrations.DeleteModel(
            name='WellnessResource',
        ),
        migrations.AlterModelOptions(
            name='medicationreminder',
            options={'ordering': ['scheduled_time']},
        ),
        migrations.RemoveField(
            model_name='medicationreminder',
            name='day_of_month',
        ),
        migrations.RemoveField(
            model_name='medicationreminder',
            name='days_of_week',
        ),
        migrations.RemoveField(
            model_name='medicationreminder',
            name='is_active',
        ),
        migrations.RemoveField(
            model_name='medicationreminder',
            name='last_sent',
        ),
        migrations.RemoveField(
            model_name='medicationreminder',
            name='next_reminder',
        ),
        migrations.RemoveField(
            model_name='medicationreminder',
            name='reminder_time',
        ),
        migrations.RemoveField(
            model_name='patient',
            name='user',
        ),
        migrations.AddField(
            model_name='medicationreminder',
            name='acknowledged_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='medicationreminder',
            name='acknowledged_time',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='medicationreminder',
            name='is_acknowledged',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='medicationreminder',
            name='is_recurring',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='medicationreminder',
            name='notification_sent',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='medicationreminder',
            name='notification_time',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='medicationreminder',
            name='recurrence_pattern',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AddField(
            model_name='medicationreminder',
            name='scheduled_time',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AlterField(
            model_name='medicationreminder',
            name='reminder_type',
            field=models.CharField(choices=[('TAKE_MED', 'Take Medication'), ('REFILL', 'Refill Needed'), ('EXPIRING', 'Prescription Expiring'), ('SIDE_CHECK', 'Side Effect Check')], max_length=15),
        ),
        migrations.AddField(
            model_name='medicationadherence',
            name='patient',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='carelink.patient'),
        ),
        migrations.DeleteModel(
            name='ExerciseLog',
        ),
        migrations.DeleteModel(
            name='MealLog',
        ),
        migrations.DeleteModel(
            name='MentalHealthLog',
        ),
        migrations.DeleteModel(
            name='NutritionPlan',
        ),
        migrations.DeleteModel(
            name='SupportGroup',
        ),
        migrations.DeleteModel(
            name='VitalSigns',
        ),
    ]
