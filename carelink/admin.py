from django.utils import timezone
from django.contrib import admin
from .models import User, Patient, HealthLog, Task, Medication, Communication, Notification, CareRequest
from django.contrib import messages
# Register User model with custom admin view
@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'user_type', 'phone_number')
    search_fields = ('username', 'email', 'phone_number')
    list_filter = ('user_type',)
    ordering = ('username',)

# Register Patient model with custom admin view
@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'date_of_birth', 'assigned_caregiver')
    search_fields = ('first_name', 'last_name', 'assigned_caregiver__username')
    list_filter = ('date_of_birth',)
    filter_horizontal = ('family_members',)

# Register HealthLog model
@admin.register(HealthLog)
class HealthLogAdmin(admin.ModelAdmin):
    list_display = ('patient', 'caregiver', 'temperature', 'blood_pressure', 'pulse_rate', 'timestamp')
    search_fields = ('patient__first_name', 'caregiver__username')
    list_filter = ('timestamp',)

# Register Task model
@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'patient', 'caregiver', 'priority', 'status', 'due_date', 'completed_at')
    search_fields = ('title', 'patient__first_name', 'caregiver__username')
    list_filter = ('priority', 'status', 'due_date')
    actions = ['mark_selected_as_completed']

    def mark_selected_as_completed(self, request, queryset):
        queryset.update(status='COMPLETED', completed_at=timezone.now())
        self.message_user(request, "Selected tasks marked as completed.")
    mark_selected_as_completed.short_description = "Mark selected tasks as completed"

# Register Medication model
@admin.register(Medication)
class MedicationAdmin(admin.ModelAdmin):
    list_display = ('name', 'patient', 'start_date', 'end_date', 'created_by')
    search_fields = ('name', 'patient__first_name', 'created_by__username')
    list_filter = ('start_date', 'end_date')

# Register Communication model
@admin.register(Communication)
class CommunicationAdmin(admin.ModelAdmin):
    list_display = ('sender', 'receiver', 'patient', 'timestamp', 'is_read')
    search_fields = ('sender__username', 'receiver__username', 'patient__first_name')
    list_filter = ('is_read', 'timestamp')

# Register Notification model
@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'type', 'title', 'is_read', 'created_at')
    search_fields = ('user__username', 'title')
    list_filter = ('type', 'is_read', 'created_at')

# Register CareRequest model
import logging
from django.contrib import admin, messages
from django.utils import timezone
from .models import CareRequest, User, Patient

# Configure logging
logger = logging.getLogger(__name__)

@admin.register(CareRequest)
class CareRequestAdmin(admin.ModelAdmin):
    list_display = ['patient_name', 'user', 'status', 'request_date']
    actions = ['approve_care_request']

    def approve_care_request(self, request, queryset):
        for care_request in queryset:
            try:
                # Log the care request details
                print(f"Approving care request: {care_request.id} for patient: {care_request.patient_name}")

                # Find an available caregiver
                caregiver = User.objects.filter(
                    user_type='CAREGIVER', 
                    assigned_patients__isnull=True
                ).first()

                if not caregiver:
                    print("No available caregiver found.")
                    self.message_user(request, "No available caregiver", messages.ERROR)
                    continue

                # Create the patient record
                patient = Patient.objects.create(
                    first_name=care_request.patient_name.split()[0],
                    last_name=care_request.patient_last_name or '',
                    date_of_birth=care_request.patient_date_of_birth or timezone.now().date(),
                    medical_condition=care_request.patient_condition or 'Not specified',
                    emergency_contact=care_request.emergency_contact or 'N/A',
                    address=care_request.patient_address or 'Not provided',
                    assigned_caregiver=caregiver
                )

                # Add family member
                patient.family_members.add(care_request.user)

                # Update care request
                care_request.status = 'APPROVED'
                care_request.caregiver = caregiver
                care_request.save()

                print(f"Patient created successfully: {patient.id}")
                self.message_user(request, f"Approved request, created patient: {patient.id}")

            except Exception as e:
                print(f"Error approving care request {care_request.id}: {str(e)}")
                self.message_user(request, f"Error: {str(e)}", messages.ERROR)

    approve_care_request.short_description = "Approve selected care requests"


from django.contrib import admin
from .models import HealthTip

@admin.register(HealthTip)
class HealthTipAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'created_at', 'updated_at')
    search_fields = ('title', 'content', 'author__username')
    list_filter = ('created_at', 'updated_at', 'author')
    ordering = ('-created_at',)