# services/health_check_service.py
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from datetime import timedelta

class HealthCheckService:
    @staticmethod
    def check_overdue_updates():
        """Check for overdue health updates and send notifications"""
        from carelink.models import HealthCheckSchedule, Notification
        
        overdue_schedules = HealthCheckSchedule.objects.filter(
            is_active=True,
            next_check__lte=timezone.now()
        )
        
        for schedule in overdue_schedules:
            # Create notification for overdue check
            Notification.objects.create(
                user=schedule.caregiver,
                type='HEALTH',
                title='Health Check Due',
                message=f'Health check is due for patient {schedule.patient.first_name} {schedule.patient.last_name}',
            )
            
            # Send email notification
            if schedule.caregiver.email:
                send_mail(
                    'Health Check Due',
                    f'A health check is due for patient {schedule.patient.first_name} {schedule.patient.last_name}',
                    settings.DEFAULT_FROM_EMAIL,
                    [schedule.caregiver.email],
                    fail_silently=True,
                )

    @staticmethod
    def get_missing_checks(caregiver):
        """Get list of missing health checks for a caregiver"""
        from carelink.models import HealthCheckSchedule
        
        return HealthCheckSchedule.objects.filter(
            caregiver=caregiver,
            is_active=True,
            next_check__lte=timezone.now()
        )

    @staticmethod
    def generate_daily_report(patient, date=None):
        """Generate a daily health report for a patient"""
        from carelink.models import HealthLog, HealthReport
        
        if date is None:
            date = timezone.now().date()
        
        logs = HealthLog.objects.filter(
            patient=patient,
            timestamp__date=date
        ).order_by('timestamp')
        
        report_data = {
            'date': date.strftime('%Y-%m-%d'),
            'patient_name': f"{patient.first_name} {patient.last_name}",
            'checks_completed': logs.count(),
            'checks_missed': 4 - logs.count(),  # 4 checks expected per day
            'vital_signs': [],
            'summary': {}
        }
        
        for log in logs:
            report_data['vital_signs'].append({
                'time': log.timestamp.strftime('%H:%M'),
                'temperature': str(log.temperature) if log.temperature else 'N/A',
                'blood_pressure': log.blood_pressure or 'N/A',
                'pulse_rate': str(log.pulse_rate) if log.pulse_rate else 'N/A',
                'oxygen_level': str(log.oxygen_level) if log.oxygen_level else 'N/A',
                'notes': log.notes
            })
        
        # Calculate averages
        if logs:
            report_data['summary'] = {
                'avg_temperature': sum(log.temperature for log in logs if log.temperature) / len([log for log in logs if log.temperature]),
                'avg_pulse_rate': sum(log.pulse_rate for log in logs if log.pulse_rate) / len([log for log in logs if log.pulse_rate]),
                'avg_oxygen_level': sum(log.oxygen_level for log in logs if log.oxygen_level) / len([log for log in logs if log.oxygen_level])
            }
        
        return HealthReport.objects.create(
            patient=patient,
            report_type='DAILY',
            report_period=1,
            report_data=report_data
        )