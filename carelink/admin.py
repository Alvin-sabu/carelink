from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.http import HttpResponseRedirect
from .models import (
    User, Patient, HealthTip, IssueReport, IssueResponse,
    HealthDocument, Task, MedicationLog, Medication, MedicationSchedule, HealthLog, Notification
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