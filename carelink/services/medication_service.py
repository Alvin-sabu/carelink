# services/medication_service.py

from django.utils import timezone
from datetime import timedelta
from ..models import Medication, MedicationInteraction, MedicationReminder, MedicationLog, MedicationSchedule
from django.db.models import Q
from django.core.mail import send_mail
from django.conf import settings

class MedicationService:
    @staticmethod
    def check_interactions(patient):
        """Check for interactions between patient's medications."""
        active_medications = patient.medications.filter(status='ACTIVE')
        interactions = []
        
        for i, med1 in enumerate(active_medications):
            for med2 in active_medications[i+1:]:
                interaction = MedicationInteraction.objects.filter(
                    Q(medication1=med1, medication2=med2) |
                    Q(medication1=med2, medication2=med1)
                ).first()
                
                if interaction:
                    interactions.append(interaction)
        
        return interactions

    @staticmethod
    def process_reminders():
        """Process due medication reminders."""
        now = timezone.now()
        due_reminders = MedicationReminder.objects.filter(
            is_sent=False,
            reminder_time__lte=now
        ).select_related('medication', 'schedule')
        
        for reminder in due_reminders:
            if reminder.reminder_type == 'UPCOMING':
                message = (
                    f"Reminder: Time to take {reminder.medication.name} "
                    f"({reminder.schedule.dosage_amount}) at {reminder.schedule.scheduled_time}"
                )
            elif reminder.reminder_type == 'MISSED':
                message = (
                    f"Alert: Missed dose of {reminder.medication.name} "
                    f"scheduled for {reminder.schedule.scheduled_time}"
                )
            else:  # REFILL
                message = (
                    f"Alert: {reminder.medication.name} needs to be refilled. "
                    f"Remaining refills: {reminder.medication.refills_remaining}"
                )
            
            # Send email notification
            send_mail(
                subject=f"Medication Reminder - {reminder.reminder_type}",
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[reminder.medication.patient.email],
                fail_silently=True
            )
            
            reminder.is_sent = True
            reminder.sent_at = now
            reminder.save()

    @staticmethod
    def check_adherence(medication, days=30):
        """Calculate medication adherence rate for the specified period."""
        end_date = timezone.now()
        start_date = end_date - timedelta(days=days)
        
        scheduled_doses = medication.schedules.count() * days
        taken_doses = MedicationLog.objects.filter(
            medication=medication,
            status='TAKEN',
            taken_at__range=(start_date, end_date)
        ).count()
        
        if scheduled_doses == 0:
            return 0
        
        return (taken_doses / scheduled_doses) * 100

    @staticmethod
    def create_missed_dose_reminders():
        """Create reminders for missed doses."""
        now = timezone.now()
        schedules = MedicationSchedule.objects.filter(
            medication__status='ACTIVE'
        ).select_related('medication')
        
        for schedule in schedules:
            scheduled_time = timezone.now().replace(
                hour=schedule.scheduled_time.hour,
                minute=schedule.scheduled_time.minute,
                second=0
            )
            
            if scheduled_time < now:
                # Check if dose was logged
                log_exists = MedicationLog.objects.filter(
                    schedule=schedule,
                    taken_at__date=now.date()
                ).exists()
                
                if not log_exists:
                    # Create missed dose reminder
                    MedicationReminder.objects.get_or_create(
                        medication=schedule.medication,
                        schedule=schedule,
                        reminder_type='MISSED',
                        reminder_time=scheduled_time + timedelta(hours=1),
                        defaults={'is_sent': False}
                    )