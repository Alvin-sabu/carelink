from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.http import HttpResponseRedirect
from .models import (
    User, Patient, HealthTip, IssueReport, IssueResponse,
    HealthDocument, Task, MedicationLog, Medication, MedicationSchedule, HealthLog, Notification,
    CareRequest
)

class CareLinkAdminSite(admin.AdminSite):
    site_header = _('CareLink Administration')
    site_title = _('CareLink Admin')
    index_title = _('CareLink Management')
    
    def each_context(self, request):
        context = super().each_context(request)
        try:
            context.update({
                'patient_count': Patient.objects.count(),
                'caregiver_count': User.objects.filter(user_type='CAREGIVER').count(),
                'task_count': Task.objects.filter(status='PENDING').count(),
                'open_issues_count': IssueReport.objects.filter(status='OPEN').count()
            })
        except Exception as e:
            print(f"Error getting counts: {e}")
            context.update({
                'patient_count': 0,
                'caregiver_count': 0,
                'task_count': 0,
                'open_issues_count': 0
            })
        return context

admin_site = CareLinkAdminSite(name='carelink_admin')

class IssueResponseInline(admin.TabularInline):
    model = IssueResponse
    extra = 1
    readonly_fields = ['created_at']

@admin.register(IssueReport, site=admin_site)
class IssueReportAdmin(admin.ModelAdmin):
    list_display = ['id', 'patient_name', 'issue_type', 'priority', 'status', 'reported_by_name', 'created_at']
    list_filter = ['status', 'priority', 'issue_type', 'created_at']
    search_fields = ['patient__first_name', 'patient__last_name', 'description']
    readonly_fields = ['created_at', 'updated_at', 'resolved_at']
    inlines = [IssueResponseInline]
    
    fieldsets = [
        ('Issue Information', {
            'fields': [
                'patient', 'reported_by', 'issue_type', 'priority', 'status',
                'description', 'created_at', 'updated_at'
            ]
        }),
        ('Resolution', {
            'fields': ['resolved_by', 'resolution_notes', 'resolved_at'],
            'classes': ['collapse'],
        }),
    ]
    
    def response_change(self, request, obj):
        if "_resolve" in request.POST:
            obj.status = 'RESOLVED'
            obj.resolved_by = request.user
            obj.resolved_at = timezone.now()
            obj.save()
            
            # Create notification for the reporting user
            Notification.objects.create(
                user=obj.reported_by,
                type='SYSTEM',
                title='Issue Resolved',
                message=f'Your reported issue has been resolved by {request.user.get_full_name()}'
            )
            
            self.message_user(request, 'Issue has been marked as resolved.')
            return HttpResponseRedirect(".")
        return super().response_change(request, obj)
    
    def patient_name(self, obj):
        return obj.patient.get_full_name()
    patient_name.short_description = 'Patient'
    
    def reported_by_name(self, obj):
        return obj.reported_by.get_full_name()
    reported_by_name.short_description = 'Reported By'

@admin.register(CareRequest, site=admin_site)
class CareRequestAdmin(admin.ModelAdmin):
    list_display = ['id', 'get_patient_name', 'request_type', 'service_type', 'status', 'request_date', 'caregiver']
    list_filter = ['status', 'request_type', 'service_type', 'request_date']
    search_fields = ['patient_name', 'patient_last_name', 'patient_condition', 'notes']
    readonly_fields = ['request_date']
    
    fieldsets = [
        ('Request Information', {
            'fields': [
                'user', 'patient', 'request_type', 'service_type', 'status', 'request_date'
            ]
        }),
        ('Patient Information', {
            'fields': [
                'patient_name', 'patient_last_name', 'patient_date_of_birth',
                'patient_condition', 'emergency_contact', 'patient_address'
            ],
        }),
        ('Service Details', {
            'fields': [
                'requested_date', 'preferred_time', 'notes', 'start_date', 'caregiver'
            ],
        }),
    ]
    
    def get_patient_name(self, obj):
        if obj.patient:
            return obj.patient.get_full_name()
        return f"{obj.patient_name} {obj.patient_last_name}"
    get_patient_name.short_description = 'Patient'
    
    def save_model(self, request, obj, form, change):
        if obj.status == 'APPROVED' and not obj.caregiver:
            obj.caregiver = request.user
        super().save_model(request, obj, form, change)

# Register other models
admin_site.register(User)
admin_site.register(Patient)
admin_site.register(HealthTip)
admin_site.register(HealthDocument)
admin_site.register(Task)
admin_site.register(MedicationLog)
admin_site.register(Medication)
admin_site.register(MedicationSchedule)
admin_site.register(HealthLog)
admin_site.register(Notification)
admin_site.register(IssueResponse)