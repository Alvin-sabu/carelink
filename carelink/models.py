from datetime import timedelta
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.urls import reverse
from django.core.exceptions import ValidationError

class User(AbstractUser):
    USER_TYPE_CHOICES = (
        ('ADMIN', 'Admin'),
        ('CAREGIVER', 'Caregiver'),
        ('FAMILY', 'Family Member')
    )
    user_type = models.CharField(max_length=10, choices=USER_TYPE_CHOICES)
    phone_number = models.CharField(max_length=15, blank=True)
    address = models.TextField(blank=True)
    profile_picture = models.ImageField(upload_to='profile_pics/', null=True, blank=True)
    family_members = models.ManyToManyField('self', blank=True, symmetrical=False, related_name='related_family_members')
    email_verified = models.BooleanField(default=True)  # Default to True for backward compatibility
    is_active = models.BooleanField(default=True)
    
    def check_email_verification(self):
        """Check if user should be considered active based on email verification"""
        # If the user was created before email verification was added,
        # consider them verified
        if self.date_joined and (timezone.now() - self.date_joined).days > 1:
            return True
        return self.email_verified or self.is_superuser

    def save(self, *args, **kwargs):
        if not self.pk:  # Only for new users
            self.email_verified = False  # New users start unverified
        super().save(*args, **kwargs)

class CareRequest(models.Model):
   REQUEST_TYPE_CHOICES = [
       ('HOME_CARE', 'Home Care'),
       ('MEDICAL_ASSISTANCE', 'Medical Assistance'),
       ('RESPITE_CARE', 'Respite Care'),
       ('SPECIALIZED_CARE', 'Specialized Care')
   ]

   user = models.ForeignKey(User, on_delete=models.CASCADE)
   patient = models.ForeignKey('Patient', on_delete=models.CASCADE, null=True, blank=True, related_name='care_requests')
   request_type = models.CharField(
       max_length=20, 
       choices=[('NEW_PATIENT', 'New Patient'), ('SERVICE', 'Service')],
       null=True, 
       blank=True
   )
   service_type = models.CharField(
       max_length=20, 
       choices=REQUEST_TYPE_CHOICES,
       null=True,
       blank=True
   )
   patient_name = models.CharField(max_length=100, null=True, blank=True)
   patient_last_name = models.CharField(max_length=100, null=True, blank=True)
   patient_date_of_birth = models.DateField(null=True, blank=True)
   patient_condition = models.TextField(null=True, blank=True)
   emergency_contact = models.CharField(max_length=15, null=True, blank=True)
   patient_address = models.TextField(null=True, blank=True)
   
   # Fields for service requests
   requested_date = models.DateField(null=True, blank=True)
   preferred_time = models.TimeField(null=True, blank=True)
   notes = models.TextField(null=True, blank=True)
   
   request_date = models.DateTimeField(auto_now_add=True)
   status = models.CharField(max_length=20, choices=[
       ('PENDING', 'Pending'), 
       ('APPROVED', 'Approved'), 
       ('REJECTED', 'Rejected')
   ], default='PENDING')
   start_date = models.DateField(null=True, blank=True)
   caregiver = models.ForeignKey(
       User, 
       on_delete=models.SET_NULL, 
       null=True, 
       blank=True, 
       related_name='assigned_care_requests'
   )

class Patient(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField()
    medical_condition = models.TextField()
    emergency_contact = models.CharField(max_length=15)
    address = models.TextField()
    family_members = models.ManyToManyField(
        User, 
        related_name='patients', 
        limit_choices_to={'user_type': 'FAMILY'}
    )
    assigned_caregiver = models.OneToOneField(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='assigned_patient', 
        limit_choices_to={'user_type': 'CAREGIVER'}
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"

    def clean(self):
        if self.assigned_caregiver:
            # Check if this caregiver is already assigned to another patient
            existing_patient = Patient.objects.filter(
                assigned_caregiver=self.assigned_caregiver
            ).exclude(pk=self.pk).first()
            
            if existing_patient:
                raise ValidationError({
                    'assigned_caregiver': f'This caregiver is already assigned to patient {existing_patient}'
                })

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

class HealthCheckSchedule(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='health_schedules')
    caregiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='health_schedules')
    last_check = models.DateTimeField(null=True, blank=True)
    next_check = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Health Check Schedule for {self.patient.first_name} {self.patient.last_name}"

    def update_schedule(self):
        """Update the next check time after a health log is submitted"""
        self.last_check = timezone.now()
        self.next_check = self.last_check + timedelta(hours=6)
        self.save()

    @property
    def is_check_due(self):
        """Check if a health check is due"""
        return timezone.now() >= self.next_check

    @property
    def time_until_next_check(self):
        """Get time remaining until next check"""
        if self.next_check:
            return self.next_check - timezone.now()
        return None

class HealthLog(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='health_logs')
    caregiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='health_logs')
    temperature = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    blood_pressure = models.CharField(max_length=20, blank=True)
    pulse_rate = models.IntegerField(null=True, blank=True)
    oxygen_level = models.IntegerField(null=True, blank=True)
    notes = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    check_schedule = models.ForeignKey(HealthCheckSchedule, on_delete=models.CASCADE, related_name='logs', null=True)

    @property
    def temperature_f(self):
        if self.temperature is None:
            return None
        return float(self.temperature) * 9/5 + 32

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.check_schedule:
            self.check_schedule.update_schedule()

    class Meta:
        ordering = ['-timestamp']

class Task(models.Model):
    PRIORITY_CHOICES = (
        ('HIGH', 'High'),
        ('MEDIUM', 'Medium'),
        ('LOW', 'Low')
    )
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('PENDING_REVIEW', 'Pending Review'),
        ('COMPLETED', 'Completed'),
        ('OVERDUE', 'Overdue')
    )
    CATEGORY_CHOICES = (
        ('MEDICATION', 'Medication'),
        ('HEALTH_CHECK', 'Health Check'),
        ('APPOINTMENT', 'Appointment'),
        ('EXERCISE', 'Exercise'),
        ('GENERAL', 'General')
    )
    
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='tasks')
    caregiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tasks')
    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='GENERAL')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='MEDIUM')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='PENDING')
    due_date = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_tasks')

    def __str__(self):
        return self.title

    def mark_for_review(self):
        self.status = 'PENDING_REVIEW'
        self.save()

    def approve_completion(self, admin_user):
        if admin_user.is_staff:
            self.status = 'COMPLETED'
            self.completed_at = timezone.now()
            self.reviewed_by = admin_user
            self.save()
        else:
            raise PermissionError("Only staff members can approve task completion")

    def mark_as_completed(self):
        self.status = 'COMPLETED'
        self.completed_at = timezone.now()
        self.save()

    class Meta:
        ordering = ['due_date', '-priority']

class Medication(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='medications')
    name = models.CharField(max_length=200)
    dosage = models.CharField(max_length=100)
    frequency = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    instructions = models.TextField()
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)

class Communication(models.Model):
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_messages')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='communications')
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    
    # New fields for attachments
    attachment = models.FileField(upload_to='message_attachments/%Y/%m/%d/', null=True, blank=True)
    attachment_type = models.CharField(max_length=50, null=True, blank=True)
    attachment_name = models.CharField(max_length=255, null=True, blank=True)
    
    class Meta:
        ordering = ['-timestamp']
        
    def __str__(self):
        return f'Message from {self.sender} to {self.receiver} at {self.timestamp}'
        
    def mark_as_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save()

class Notification(models.Model):
    TYPE_CHOICES = (
        ('TASK', 'Task Update'),
        ('HEALTH', 'Health Update'),
        ('MESSAGE', 'New Message'),
        ('SYSTEM', 'System Notification')
    )
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
class HealthAnalysis(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='health_analyses')
    analyzed_date = models.DateTimeField(auto_now_add=True)
    
    # Vital Statistics Analysis
    avg_temperature = models.DecimalField(max_digits=4, decimal_places=1, null=True)
    avg_blood_pressure = models.CharField(max_length=20, null=True)
    avg_pulse_rate = models.IntegerField(null=True)
    avg_oxygen_level = models.IntegerField(null=True)
    
    # Risk Assessment
    RISK_LEVELS = (
        ('LOW', 'Low Risk'),
        ('MODERATE', 'Moderate Risk'),
        ('HIGH', 'High Risk')
    )
    risk_level = models.CharField(max_length=10, choices=RISK_LEVELS)
    risk_factors = models.TextField()
    recommendations = models.TextField()

    @property
    def avg_temperature_f(self):
        if self.avg_temperature is None:
            return None
        return float(self.avg_temperature) * 9/5 + 32

class HealthReport(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='health_reports')
    generated_date = models.DateTimeField(auto_now_add=True)
    report_period = models.IntegerField(help_text="Report period in days")
    report_data = models.TextField()
    
    REPORT_TYPES = (
        ('DAILY', 'Daily Report'),
        ('WEEKLY', 'Weekly Report'),
        ('MONTHLY', 'Monthly Report')
    )
    report_type = models.CharField(max_length=10, choices=REPORT_TYPES)


class HealthTip(models.Model):
    CATEGORY_CHOICES = [
        ('GENERAL', 'General Health'),
        ('NUTRITION', 'Nutrition'),
        ('FITNESS', 'Fitness'),
        ('MENTAL', 'Mental Health'),
        ('ELDERLY', 'Elderly Care'),
        ('PEDIATRIC', 'Pediatric Care'),
        ('CHRONIC', 'Chronic Disease Management'),
        ('PREVENTIVE', 'Preventive Care'),
    ]

    title = models.CharField(max_length=200)
    content = models.TextField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='GENERAL')
    image = models.ImageField(upload_to='health_tips/', null=True, blank=True)
    source = models.URLField(max_length=500, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    author = models.ForeignKey(User, on_delete=models.CASCADE)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-created_at']

class HealthDocument(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    document = models.FileField(upload_to='health_documents/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title
    

# models.py

from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone

class Medication(models.Model):
    FREQUENCY_CHOICES = [
        ('DAILY', 'Daily'),
        ('TWICE_DAILY', 'Twice Daily'),
        ('THREE_TIMES_DAILY', 'Three Times Daily'),
        ('FOUR_TIMES_DAILY', 'Four Times Daily'),
        ('WEEKLY', 'Weekly'),
        ('AS_NEEDED', 'As Needed'),
    ]

    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('COMPLETED', 'Completed'),
        ('DISCONTINUED', 'Discontinued'),
    ]

    patient = models.ForeignKey('Patient', on_delete=models.CASCADE, related_name='medications')
    name = models.CharField(max_length=200)
    dosage = models.CharField(max_length=100)
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    prescription_number = models.CharField(max_length=50, null=True, blank=True)
    prescribing_doctor = models.CharField(max_length=200)
    pharmacy_name = models.CharField(max_length=200, null=True, blank=True)
    pharmacy_phone = models.CharField(max_length=20, null=True, blank=True)
    refills_remaining = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    next_refill_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    instructions = models.TextField(blank=True)  # Ensure this field is included
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    created_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class MedicationSchedule(models.Model):
    medication = models.ForeignKey(Medication, on_delete=models.CASCADE, related_name='schedules')
    scheduled_time = models.TimeField()
    dosage_amount = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.medication.name} at {self.scheduled_time}"
    

from django.db import models
from django.utils import timezone

class MedicationLog(models.Model):
    STATUS_CHOICES = [
        ('TAKEN', 'Taken'),
        ('MISSED', 'Missed'),
        ('SKIPPED', 'Skipped'),
        ('RESCHEDULED', 'Rescheduled')
    ]
    
    medication = models.ForeignKey('Medication', on_delete=models.CASCADE, related_name='logs')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    notes = models.TextField(blank=True)
    taken_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.medication.name} - {self.status} at {self.taken_at}"

class HealthInsight(models.Model):
    SEVERITY_CHOICES = [
        ('LOW', 'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH', 'High'),
    ]
    
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='health_insights')
    type = models.CharField(max_length=50)
    message = models.TextField()
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']

class HealthPrediction(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='health_predictions')
    predicted_temperature = models.FloatField(null=True, blank=True)
    predicted_systolic_bp = models.IntegerField(null=True, blank=True)
    predicted_diastolic_bp = models.IntegerField(null=True, blank=True)
    predicted_pulse_rate = models.IntegerField(null=True, blank=True)
    predicted_oxygen_level = models.IntegerField(null=True, blank=True)
    confidence_score = models.FloatField()
    prediction_time = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

class MLRecommendation(models.Model):
    TYPE_CHOICES = [
        ('URGENT', 'Urgent'),
        ('MONITOR', 'Monitor'),
        ('ANOMALY', 'Anomaly'),
        ('PREDICTIVE', 'Predictive'),
    ]
    
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='ml_recommendations')
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    message = models.TextField()
    action_required = models.BooleanField(default=False)
    is_addressed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    addressed_at = models.DateTimeField(null=True, blank=True)
    addressed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

class MLPrediction(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='ml_predictions', null=True)
    predicted_temperature = models.FloatField()
    prediction_time = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-prediction_time']

class MLInsight(models.Model):
    INSIGHT_TYPES = [
        ('TREND', 'Trend'),
        ('ANOMALY', 'Anomaly'),
        ('PATTERN', 'Pattern'),
    ]
    
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='ml_insights', null=True)
    insight_type = models.CharField(max_length=20, choices=INSIGHT_TYPES)
    description = models.TextField()
    confidence = models.FloatField()  # 0-100
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']

class MLRecommendation(models.Model):
    RECOMMENDATION_TYPES = [
        ('CARE', 'Care'),
        ('ALERT', 'Alert'),
        ('LIFESTYLE', 'Lifestyle'),
    ]
    
    PRIORITY_LEVELS = [
        ('LOW', 'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH', 'High'),
    ]
    
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='ml_recommendations', null=True)
    recommendation_type = models.CharField(max_length=20, choices=RECOMMENDATION_TYPES)
    description = models.TextField()
    priority = models.CharField(max_length=10, choices=PRIORITY_LEVELS)
    based_on_insight = models.ForeignKey(MLInsight, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_addressed = models.BooleanField(default=False)
    addressed_at = models.DateTimeField(null=True, blank=True)
    addressed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='addressed_recommendations')
    
    class Meta:
        ordering = ['-created_at']

class IssueReport(models.Model):
    ISSUE_TYPE_CHOICES = [
        ('CARE_QUALITY', 'Care Quality Concern'),
        ('COMMUNICATION', 'Communication Problem'),
        ('MEDICATION', 'Medication Issue'),
        ('SCHEDULING', 'Scheduling Problem'),
        ('OTHER', 'Other')
    ]
    
    PRIORITY_CHOICES = [
        ('LOW', 'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH', 'High'),
        ('URGENT', 'Urgent')
    ]
    
    STATUS_CHOICES = [
        ('OPEN', 'Open'),
        ('IN_PROGRESS', 'In Progress'),
        ('RESOLVED', 'Resolved'),
        ('CLOSED', 'Closed')
    ]
    
    patient = models.ForeignKey('Patient', on_delete=models.CASCADE, related_name='issue_reports')
    reported_by = models.ForeignKey('User', on_delete=models.CASCADE, related_name='reported_issues')
    issue_type = models.CharField(max_length=20, choices=ISSUE_TYPE_CHOICES)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES)
    description = models.TextField()
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='OPEN')
    resolution_notes = models.TextField(blank=True)
    resolved_by = models.ForeignKey(
        'User', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='resolved_issues'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Issue Report #{self.id} - {self.get_issue_type_display()}"

    def resolve(self, user, notes):
        self.status = 'RESOLVED'
        self.resolved_by = user
        self.resolution_notes = notes
        self.resolved_at = timezone.now()
        self.save()

class IssueResponse(models.Model):
    issue = models.ForeignKey(IssueReport, on_delete=models.CASCADE, related_name='responses')
    responder = models.ForeignKey('User', on_delete=models.CASCADE)
    response = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Response to Issue #{self.issue.id} by {self.responder.get_full_name()}"