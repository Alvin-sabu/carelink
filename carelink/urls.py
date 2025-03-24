from django.urls import path, re_path
from . import views
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from django.contrib.auth import views as auth_views
from .views import (
    CustomPasswordResetView,
    CustomPasswordResetDoneView,
    CustomPasswordResetConfirmView,
    CustomPasswordResetCompleteView
)

app_name = 'carelink'

urlpatterns = [
    path('', views.HomeView.as_view(), name='home'),
    path('register/', views.RegisterView.as_view(), name='register'),
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('profile/update/', views.ProfileUpdateView.as_view(), name='profile_update'),
    path('caregiver/dashboard/', views.CaregiverDashboardView.as_view(), name='caregiver_dashboard'),
    path('family/dashboard/', views.FamilyDashboardView.as_view(), name='family_dashboard'),
    path('patient/<int:pk>/', views.PatientDetailView.as_view(), name='patient_detail'),
    path('patient/<int:pk>/health-log/add/', views.AddHealthLogView.as_view(), name='add_health_log'),
    path('task/<int:pk>/complete/', views.complete_task, name='complete_task'),
    path('task/list/', views.TaskListView.as_view(), name='task_list'),
    path('care-requests/', views.CareRequestListView.as_view(), name='care_request_list'),
    path('notifications/', views.NotificationsView.as_view(), name='notifications_list'),
    path('notifications/<int:notification_id>/mark-read/', views.mark_notification_read, name='mark_notification_read'),
    path('notifications/mark-all-read/', views.mark_all_notifications_read, name='mark_all_notifications_read'),
    path('messages/', views.MessagesListView.as_view(), name='messages_list'),
    path('conversation/<int:user_id>/<int:patient_id>/', views.ConversationView.as_view(), name='conversation'),
    path('message/send/', views.send_message, name='send_message'),
    path('message/<int:message_id>/mark-read/', views.mark_message_read, name='mark_message_read'),
    path('message/<int:message_id>/attachment/', views.download_attachment, name='download_attachment'),
    path('task/add/', views.AddTaskView.as_view(), name='add_task'),
    path('patient/<int:pk>/medication/add/', views.AddMedicationView.as_view(), name='add_medication'),
    path('patient/<int:patient_id>/health/', views.HealthDashboardView.as_view(), name='health_dashboard'),
    path('patient/<int:patient_id>/report/', views.GenerateHealthReportView.as_view(), name='generate_health_report'),
    path('submit-care-request/', views.submit_care_request, name='submit_care_request'),
    path('health-documents/', views.HealthDocumentListView.as_view(), name='health_document_list'),
    path('health-documents/add/', views.HealthDocumentCreateView.as_view(), name='health_document_create'),
    path('health-documents/<int:pk>/', views.HealthDocumentDetailView.as_view(), name='health_document_detail'),
    path('health-documents/<int:pk>/edit/', views.HealthDocumentUpdateView.as_view(), name='health_document_update'),
    path('health-documents/<int:pk>/delete/', views.HealthDocumentDeleteView.as_view(), name='health_document_delete'),
    
    # Health Tips URLs
    path('health-tips/', views.HealthTipListView.as_view(), name='health_tips_list'),
    path('health-tips/add/', views.HealthTipCreateView.as_view(), name='health_tip_create'),
    path('health-tips/<int:pk>/', views.HealthTipDetailView.as_view(), name='health_tip_detail'),
    path('health-tips/<int:pk>/edit/', views.HealthTipUpdateView.as_view(), name='health_tip_update'),
    path('health-tips/<int:pk>/delete/', views.HealthTipDeleteView.as_view(), name='health_tip_delete'),
    
    # API endpoints
    path('api/recommendations/<int:rec_id>/mark-addressed/', views.mark_recommendation_addressed, name='mark_recommendation_addressed'),
    path('api/patient/<int:patient_id>/recommendations/', views.get_ai_recommendations, name='get_ai_recommendations'),
    path('api/patient/<int:patient_id>/next-appointment/', views.get_patient_next_appointment, name='get_patient_next_appointment'),
    path('api/patient/<int:patient_id>/medication-adherence/', views.get_patient_medication_adherence, name='get_patient_medication_adherence'),
    path('api/patient/<int:patient_id>/alerts/', views.get_patient_alerts, name='get_patient_alerts'),
    path('api/patient/<int:patient_id>/task-progress/', views.get_patient_task_progress, name='get_patient_task_progress'),
    path('api/medications/<int:medication_id>/update-status/', views.update_medication_status, name='update_medication_status'),
    path('api/patient/<int:patient_id>/medication/add/', views.add_medication, name='add_medication'),
    path('api/medication/mark-taken/', views.mark_medication_taken, name='mark_medication_taken'),
    path('api/report-issue/', views.report_issue, name='report_issue'),
    
    # Health recommendation views
    path('recommendations/', views.recommendations_view, name='recommendations'),
    path('get_ai_recommendations/<int:patient_id>/', views.get_ai_recommendations, name='get_ai_recommendations'),
    
    # Issue management
    path('issues/', views.issue_management, name='issue_management'),
    path('api/issue-detail/', views.issue_detail, name='issue_detail'),
    path('api/respond-to-issue/', views.respond_to_issue, name='respond_to_issue'),
    
    # Authentication URLs
    path('accounts/logout/', auth_views.LogoutView.as_view(next_page='carelink:home'), name='logout'),
    path('accounts/password_reset/', CustomPasswordResetView.as_view(), name='password_reset'),
    path('accounts/password_reset/done/', CustomPasswordResetDoneView.as_view(), name='password_reset_done'),
    path('accounts/reset/<uidb64>/<token>/', CustomPasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('accounts/reset/done/', CustomPasswordResetCompleteView.as_view(), name='password_reset_complete'),
    
    # Media files
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    
    # Static Pages
    path('about/', views.AboutUsView.as_view(), name='about'),
    path('contact/', views.ContactView.as_view(), name='contact'),
    path('privacy/', views.PrivacyPolicyView.as_view(), name='privacy'),
    
    # Task Management URLs
    path('task/<int:task_id>/mark-review/', views.mark_task_for_review, name='mark_task_for_review'),
    path('task/<int:task_id>/approve/', views.approve_task, name='approve_task'),
    path('task/<int:task_id>/', views.get_task, name='get_task'),
    path('task/<int:task_id>/edit/', views.edit_task, name='edit_task'),
    path('task/<int:task_id>/delete/', views.delete_task, name='delete_task'),
    path('task/<int:task_id>/complete/', views.complete_task, name='complete_task'),
    
    # Health Dashboard API endpoints
    path('api/patient/<int:patient_id>/vitals/', views.get_vitals_data, name='get_vitals_data'),
    path('api/patient/<int:patient_id>/health-metrics/', views.get_health_metrics, name='get_health_metrics'),
    path('api/patient/<int:patient_id>/recent-activities/', views.get_recent_activities, name='get_recent_activities'),
    path('verify-email/<str:uidb64>/<str:token>/', views.VerifyEmailView.as_view(), name='verify_email'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)