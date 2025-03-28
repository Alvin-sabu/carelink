# Generated by Django 5.1.7 on 2025-03-15 13:44

import datetime
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('carelink', '0015_medicationadherence_medicationinteraction_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='TaskAttachment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file', models.FileField(upload_to='task_attachments/')),
                ('filename', models.CharField(max_length=255)),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name='TaskComment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('comment', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.RemoveField(
            model_name='medicationadherence',
            name='medication',
        ),
        migrations.RemoveField(
            model_name='medicationadherence',
            name='patient',
        ),
        migrations.AlterUniqueTogether(
            name='medicationinteraction',
            unique_together=None,
        ),
        migrations.RemoveField(
            model_name='medicationinteraction',
            name='medication1',
        ),
        migrations.RemoveField(
            model_name='medicationinteraction',
            name='medication2',
        ),
        migrations.RemoveField(
            model_name='medicationinventory',
            name='medication',
        ),
        migrations.RemoveField(
            model_name='medicationreminder',
            name='acknowledged_by',
        ),
        migrations.RemoveField(
            model_name='medicationreminder',
            name='medication',
        ),
        migrations.RemoveField(
            model_name='medicationsideeffect',
            name='medication',
        ),
        migrations.AlterModelOptions(
            name='task',
            options={'ordering': ['due_date', '-priority']},
        ),
        migrations.AddField(
            model_name='task',
            name='category',
            field=models.CharField(choices=[('MEDICATION', 'Medication'), ('HEALTH_CHECK', 'Health Check'), ('APPOINTMENT', 'Appointment'), ('EXERCISE', 'Exercise'), ('DIET', 'Diet'), ('OTHER', 'Other')], default='OTHER', max_length=20),
        ),
        migrations.AddField(
            model_name='task',
            name='completed_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='completed_tasks', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='task',
            name='custom_recurrence',
            field=models.CharField(blank=True, help_text="Custom recurrence pattern (e.g., 'every 3 days')", max_length=50),
        ),
        migrations.AddField(
            model_name='task',
            name='estimated_duration',
            field=models.DurationField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='task',
            name='is_recurring',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='task',
            name='last_reminder_sent',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='task',
            name='parent_task',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='recurring_instances', to='carelink.task'),
        ),
        migrations.AddField(
            model_name='task',
            name='recurrence_end_date',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='task',
            name='recurrence_type',
            field=models.CharField(choices=[('NONE', 'No Recurrence'), ('DAILY', 'Daily'), ('WEEKLY', 'Weekly'), ('MONTHLY', 'Monthly'), ('CUSTOM', 'Custom')], default='NONE', max_length=10),
        ),
        migrations.AddField(
            model_name='task',
            name='reminder_before',
            field=models.DurationField(default=datetime.timedelta(seconds=3600)),
        ),
        migrations.AddField(
            model_name='task',
            name='reminder_enabled',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='task',
            name='start_date',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AddField(
            model_name='task',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddIndex(
            model_name='task',
            index=models.Index(fields=['due_date', 'status'], name='carelink_ta_due_dat_d5a10d_idx'),
        ),
        migrations.AddIndex(
            model_name='task',
            index=models.Index(fields=['patient', 'status'], name='carelink_ta_patient_20a6f1_idx'),
        ),
        migrations.AddIndex(
            model_name='task',
            index=models.Index(fields=['caregiver', 'status'], name='carelink_ta_caregiv_bd105f_idx'),
        ),
        migrations.AddField(
            model_name='taskattachment',
            name='task',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attachments', to='carelink.task'),
        ),
        migrations.AddField(
            model_name='taskattachment',
            name='uploaded_by',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='taskcomment',
            name='task',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='comments', to='carelink.task'),
        ),
        migrations.AddField(
            model_name='taskcomment',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL),
        ),
        migrations.DeleteModel(
            name='MedicationAdherence',
        ),
        migrations.DeleteModel(
            name='MedicationInteraction',
        ),
        migrations.DeleteModel(
            name='MedicationInventory',
        ),
        migrations.DeleteModel(
            name='MedicationReminder',
        ),
        migrations.DeleteModel(
            name='MedicationSideEffect',
        ),
    ]
