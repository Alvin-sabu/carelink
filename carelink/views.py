import json
import logging
import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.decorators import login_required
from django.views.generic import ListView, CreateView, DetailView, UpdateView, DeleteView, View, TemplateView
from django.urls import reverse_lazy, reverse
from django.db.models import Q, Avg, Count
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from .models import (
    User, Patient, Task, Medication, Communication,
    CareRequest, Notification, HealthLog, HealthCheckSchedule,
    HealthAnalysis, HealthTip, HealthDocument, HealthInsight, HealthPrediction, MLRecommendation,
    MLPrediction, MLInsight, HealthReport, MedicationSchedule, MedicationLog
)
from .forms import (
    TaskForm, MedicationForm, CommunicationForm, CareRequestForm,
    HealthLogForm, HealthCheckScheduleForm, HealthDocumentForm,
    UserProfileUpdateForm, UserRegistrationForm
)
from datetime import timedelta, datetime
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from .services.health_analyzer import HealthAnalyzer
from .services.ml_service import HealthMLService
from django.core.mail import send_mail, EmailMultiAlternatives
from django.core.serializers.json import DjangoJSONEncoder
from django.core.exceptions import PermissionDenied
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.views import PasswordResetView, PasswordResetDoneView, PasswordResetConfirmView, PasswordResetCompleteView
from django.contrib.auth.forms import PasswordResetForm
from django.views import View
import decimal
from django.core.exceptions import PermissionDenied
from django.contrib.auth import logout
from django.template import loader

logger = logging.getLogger(__name__)

class DecimalEncoder(DjangoJSONEncoder):
    def default(self, obj):
        if isinstance(obj, decimal.Decimal):
            return float(obj)
        return super().default(obj)

class CustomLogoutView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        logout(request)
        return redirect('login')

class RegisterView(CreateView):
    form_class = UserRegistrationForm
    template_name = 'carelink/register.html'
    success_url = reverse_lazy('login')
    
    def form_valid(self, form):
        response = super().form_valid(form)
        user = form.save(commit=False)
        user.is_active = True  # We'll control access through email_verified
        user.save()
        
        # Handle profile picture
        if 'profile_picture' in self.request.FILES:
            user.profile_picture = self.request.FILES['profile_picture']
            user.save()
        
        # Generate verification token
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.http import urlsafe_base64_encode
        from django.utils.encoding import force_bytes
        
        # Create verification URL
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        verification_url = self.request.build_absolute_uri(
            reverse('carelink:verify_email', kwargs={'uidb64': uid, 'token': token})
        )
        
        # Prepare email context
        context = {
            'user': user,
            'verification_url': verification_url,
            'protocol': 'https' if self.request.is_secure() else 'http',
            'domain': self.request.get_host(),
            'site_name': 'CareLink',
        }
        
        # Render email templates
        subject = 'Welcome to CareLink - Please Verify Your Email'
        text_content = loader.render_to_string('registration/registration_email.txt', context)
        html_content = loader.render_to_string('registration/registration_email.html', context)
        
        # Create and send email
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email]
        )
        email.attach_alternative(html_content, "text/html")
        email.send()
        
        # Add success message
        messages.success(
            self.request, 
            'Account created successfully! Please check your email to verify your account. '
            'You will not be able to log in until you verify your email address.'
        )
        
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Create Account'
        return context

class HomeView(TemplateView):
    template_name = 'carelink/home.html'
    
    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            if not request.user.check_email_verification() and not request.user.is_superuser:
                messages.warning(request, 'Please verify your email address before accessing the dashboard.')
                return redirect('login')
            if request.user.user_type == 'CAREGIVER':
                return redirect('carelink:caregiver_dashboard')
            elif request.user.user_type == 'FAMILY':
                return redirect('carelink:family_dashboard')
        return super().get(request, *args, **kwargs)

@login_required
def submit_care_request(request):
    if request.method == 'POST':
        request_type = request.POST.get('request_type')
        service_type = request.POST.get('service_type')
        
        # Debug messages
        print(f"Received POST data: {request.POST}")
        print(f"request_type: {request_type}")
        print(f"service_type: {service_type}")
        
        # Validate service type
        if not service_type:
            messages.error(request, 'Please select a service type.')
            return redirect('carelink:care_request_list')
            
        # Validate request type
        if request_type not in ['NEW_PATIENT', 'SERVICE']:
            messages.error(request, 'Invalid request type.')
            return redirect('carelink:care_request_list')
            
        if request_type == 'NEW_PATIENT':
            # Handle new patient care request
            required_fields = [
                'patient_name', 'patient_last_name', 'patient_date_of_birth',
                'patient_condition', 'emergency_contact', 'patient_address',
                'service_type'  # Add service_type to required fields
            ]
            
            # Check required fields
            missing_fields = [field for field in required_fields if not request.POST.get(field)]
            if missing_fields:
                messages.error(request, f'Please fill in all required fields: {", ".join(missing_fields)}')
                return redirect('carelink:care_request_list')
                
            try:
                care_request = CareRequest.objects.create(
                    user=request.user,
                    request_type=request_type,
                    service_type=service_type,
                    patient_name=request.POST['patient_name'],
                    patient_last_name=request.POST['patient_last_name'],
                    patient_date_of_birth=request.POST['patient_date_of_birth'],
                    patient_condition=request.POST['patient_condition'],
                    emergency_contact=request.POST['emergency_contact'],
                    patient_address=request.POST['patient_address'],
                    status='PENDING'
                )
                messages.success(request, 'Care request for new patient submitted successfully.')
                return redirect('carelink:care_request_list')
            except Exception as e:
                messages.error(request, f'Error submitting care request: {str(e)}')
                return redirect('carelink:care_request_list')
                
        elif request_type == 'SERVICE':
            # Handle service request for existing patient
            required_fields = ['patient_id', 'requested_date', 'preferred_time', 'service_type']
            
            # Check required fields
            missing_fields = [field for field in required_fields if not request.POST.get(field)]
            if missing_fields:
                messages.error(request, f'Please fill in all required fields: {", ".join(missing_fields)}')
                return redirect('carelink:care_request_list')
                
            try:
                patient = Patient.objects.get(id=request.POST['patient_id'], family_members=request.user)
                care_request = CareRequest.objects.create(
                    user=request.user,
                    patient=patient,
                    request_type=request_type,
                    service_type=service_type,
                    requested_date=request.POST['requested_date'],
                    preferred_time=request.POST['preferred_time'],
                    notes=request.POST.get('notes', ''),
                    status='PENDING'
                )
                messages.success(request, 'Service request submitted successfully.')
                return redirect('carelink:care_request_list')
            except Patient.DoesNotExist:
                messages.error(request, 'Invalid patient selected.')
                return redirect('carelink:care_request_list')
            except Exception as e:
                messages.error(request, f'Error submitting service request: {str(e)}')
                return redirect('carelink:care_request_list')
    
    return redirect('carelink:care_request_list')

class CaregiverDashboardView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = Patient
    template_name = 'carelink/caregiver_dashboard.html'
    context_object_name = 'patients'

    def test_func(self):
        return self.request.user.user_type == 'CAREGIVER'

    def get_queryset(self):
        try:
            if hasattr(self.request.user, 'assigned_patient'):
                return Patient.objects.filter(id=self.request.user.assigned_patient.id)
            return Patient.objects.none()
        except User.assigned_patient.RelatedObjectDoesNotExist:
            return Patient.objects.none()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Check if user has assigned patients
        context['has_patients'] = hasattr(self.request.user, 'assigned_patient')
        
        if context['has_patients']:
            patient = self.request.user.assigned_patient
            current_time = timezone.now()
            
            # Get next appointment from health check schedule
            next_appointment = HealthCheckSchedule.objects.filter(
                patient=patient,
                caregiver=self.request.user,
                is_active=True,
                next_check__gte=current_time
            ).order_by('next_check').first()
            context['next_appointment'] = next_appointment
            
            # Calculate medication adherence
            end_date = current_time
            start_date = end_date - timedelta(days=30)
            
            # Get all active medications for the patient
            active_medications = Medication.objects.filter(
                patient=patient,
                status='ACTIVE'
            ).prefetch_related('schedules', 'logs')
            
            total_scheduled_doses = 0
            total_taken_doses = 0
            
            for medication in active_medications:
                # Count scheduled doses
                daily_doses = medication.schedules.count()
                days_active = min(30, (end_date.date() - medication.start_date).days + 1)
                if days_active > 0:
                    total_scheduled_doses += daily_doses * days_active
                
                # Count taken doses
                taken_doses = medication.logs.filter(
                    status='TAKEN',
                    taken_at__range=(start_date, end_date)
                ).count()
                total_taken_doses += taken_doses
            
            # Calculate adherence rate
            context['medication_adherence'] = round((total_taken_doses / total_scheduled_doses * 100) if total_scheduled_doses > 0 else 100)
            context['active_medications'] = active_medications
            
            # Get tasks - using status field instead of is_completed
            context['tasks'] = Task.objects.filter(
                patient=patient,
                status__in=['PENDING', 'IN_PROGRESS']
            )
            context['overdue_tasks'] = context['tasks'].filter(
                due_date__lt=timezone.now()
            )
            
            # Get health checks
            context['upcoming_checks'] = HealthCheckSchedule.objects.filter(
                patient=patient,
                caregiver=self.request.user,
                is_active=True,
                next_check__gte=timezone.now()
            ).order_by('next_check')[:5]
            
            # Get recent documents
            context['recent_documents'] = HealthDocument.objects.filter(
                user=self.request.user
            ).order_by('-uploaded_at')[:5]
            
            # Get recent health logs
            context['recent_health_logs'] = HealthLog.objects.filter(
                patient=patient,
                caregiver=self.request.user
            ).order_by('-timestamp')[:5]
            
            # Add current time for template comparisons
            context['now'] = timezone.now()
        
        return context

class FamilyDashboardView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = Patient
    template_name = 'carelink/family_dashboard.html'
    context_object_name = 'patients'

    def test_func(self):
        return self.request.user.user_type == 'FAMILY'

    def get_queryset(self):
        # Get patients with all related data in a single query
        return Patient.objects.filter(
            family_members=self.request.user
        ).prefetch_related(
            'health_logs',
            'health_analyses',
            'medications',
            'tasks',
            'assigned_caregiver'
        ).order_by('first_name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        current_time = timezone.now()
        patients = self.get_queryset()
        context['has_patients'] = patients.exists()

        # Add patient-specific data
        patient_data = {}
        for patient in patients:
            # Convert patient.id to string for dictionary key
            patient_id = str(patient.id)
            
            # Get active medications with their next scheduled dose
            active_medications = patient.medications.filter(
                end_date__gte=current_time,
                status='ACTIVE'
            ).prefetch_related('schedules').order_by('start_date')[:5]
            
            # Format medication data with next dose information
            medication_data = []
            for med in active_medications:
                next_schedule = med.schedules.filter(
                    scheduled_time__gte=current_time
                ).order_by('scheduled_time').first()
                
                medication_data.append({
                    'name': med.name,
                    'next_dose': next_schedule.scheduled_time if next_schedule else None,
                    'dosage': med.dosage,
                    'instructions': med.instructions
                })

            # Get recent health logs
            recent_health_logs = list(patient.health_logs.all().order_by('-timestamp')[:5])

            # Get upcoming tasks
            upcoming_tasks = list(patient.tasks.filter(
                status__in=['PENDING', 'IN_PROGRESS'],
                due_date__gte=current_time
            ).order_by('due_date')[:5])

            patient_data[patient_id] = {
                'recent_health_logs': recent_health_logs,
                'recent_medications': medication_data,
                'upcoming_tasks': upcoming_tasks
            }

        context['patient_data'] = patient_data
        return context
    
    
class PatientDetailView(LoginRequiredMixin, DetailView):
    model = Patient
    template_name = 'carelink/patient_detail.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['health_logs'] = self.object.health_logs.order_by('-timestamp')[:10]
        context['tasks'] = self.object.tasks.order_by('-created_at')[:10]
        context['medications'] = self.object.medications.all()
        context['health_log_form'] = HealthLogForm()
        context['medication_form'] = MedicationForm()
        context['task_form'] = TaskForm()
        return context

class AddHealthLogView(LoginRequiredMixin, CreateView):
    model = HealthLog
    form_class = HealthLogForm
    template_name = 'carelink/add_health_log.html'
    
    def form_valid(self, form):
        patient = get_object_or_404(Patient, pk=self.kwargs['pk'])
        form.instance.patient = patient
        form.instance.caregiver = self.request.user
        
        # Get the most recent active schedule or create a new one
        schedule = HealthCheckSchedule.objects.filter(
            patient=patient,
            caregiver=self.request.user,
            is_active=True
        ).order_by('-next_check').first()
        
        if not schedule:
            schedule = HealthCheckSchedule.objects.create(
                patient=patient,
                caregiver=self.request.user,
                next_check=timezone.now() + timedelta(hours=6),
                is_active=True
            )
        
        form.instance.check_schedule = schedule
        response = super().form_valid(form)
        
        messages.success(self.request, 'Health log added successfully. Next check due in 6 hours.')
        return response

    def get_success_url(self):
        return reverse_lazy('carelink:patient_detail', kwargs={'pk': self.kwargs['pk']})

class AddTaskView(LoginRequiredMixin, CreateView):
    model = Task
    form_class = TaskForm
    template_name = 'carelink/task_form.html'
    success_url = reverse_lazy('carelink:task_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Add New Task'
        return context

    def form_valid(self, form):
        form.instance.caregiver = self.request.user
        form.instance.patient = form.cleaned_data['patient']
        response = super().form_valid(form)
        
        # If this is a health check task, create a HealthCheckSchedule entry
        if form.instance.category == 'HEALTH_CHECK':
            HealthCheckSchedule.objects.create(
                patient=form.instance.patient,
                caregiver=self.request.user,
                next_check=form.instance.due_date,
                is_active=True
            )
        
        return response

@login_required
@require_http_methods(['POST'])
def complete_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)

    # Ensure only the assigned caregiver can mark task for review
    if request.user != task.caregiver:
        return JsonResponse({'success': False, 'error': 'You are not assigned to this task'}, status=403)

    try:
        task.mark_for_review()
        # Create notification for admin
        Notification.objects.create(
            user=User.objects.filter(is_staff=True).first(),
            type='TASK',
            title='Task Review Required',
            message=f'Task "{task.title}" needs review for completion'
        )
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    return JsonResponse({'success': False, 'error': 'Invalid request method'}, status=400)

class MessagesView(LoginRequiredMixin, ListView):
    model = Communication
    template_name = 'carelink/messages.html'
    context_object_name = 'conversations'

    def get_queryset(self):
        user = self.request.user
        
        # Get all patients related to the user
        if user.user_type == 'CAREGIVER':
            patients = Patient.objects.filter(assigned_caregiver=user)
        else:  # FAMILY
            patients = Patient.objects.filter(family_members=user)
        
        # Get unique conversations for each patient
        conversations = []
        for patient in patients:
            if user.user_type == 'CAREGIVER':
                other_user = patient.family_members.first()
            else:  # FAMILY
                other_user = patient.assigned_caregiver
            
            if other_user:
                # Get latest message for this conversation
                latest_message = Communication.objects.filter(
                    Q(sender=user, receiver=other_user, patient=patient) |
                    Q(sender=other_user, receiver=user, patient=patient)
                ).order_by('-timestamp').first()
                
                if latest_message:
                    conversations.append({
                        'patient': patient,
                        'other_user': other_user,
                        'latest_message': latest_message,
                        'unread_count': Communication.objects.filter(
                            sender=other_user,
                            receiver=user,
                            patient=patient,
                            is_read=False
                        ).count()
                    })
        
        return sorted(conversations, key=lambda x: x['latest_message'].timestamp, reverse=True)

class ConversationView(LoginRequiredMixin, ListView):
    model = Communication
    template_name = 'carelink/conversation.html'
    context_object_name = 'messages'

    def get_queryset(self):
        user = self.request.user
        other_user_id = self.kwargs.get('user_id')
        patient_id = self.kwargs.get('patient_id')
        
        # Get all messages between these users for this patient
        messages = Communication.objects.filter(
            Q(sender=user, receiver_id=other_user_id, patient_id=patient_id) |
            Q(sender_id=other_user_id, receiver=user, patient_id=patient_id)
        ).order_by('timestamp')
        
        # Mark unread messages as read
        messages.filter(receiver=user, is_read=False).update(is_read=True)
        
        return messages

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        patient_id = self.kwargs.get('patient_id')
        other_user_id = self.kwargs.get('user_id')
        
        context['patient'] = get_object_or_404(Patient, id=patient_id)
        context['other_user'] = get_object_or_404(User, id=other_user_id)
        return context

class HealthTipListView(ListView):
    model = HealthTip
    template_name = 'carelink/health_tips_list.html'
    context_object_name = 'health_tips'

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return HealthTip.objects.all()
        else:
            return HealthTip.objects.filter(
                Q(author__in=User.objects.filter(assigned_patients__in=user.assigned_patients.all())) |
                Q(category__in=['GENERAL', 'ELDERLY', 'PREVENTIVE'])
            ).distinct()

class HealthTipCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = HealthTip
    template_name = 'carelink/health_tip_form.html'
    fields = ['title', 'content', 'category', 'image', 'source']
    success_url = reverse_lazy('carelink:health_tips_list')

    def test_func(self):
        return self.request.user.is_staff

    def form_valid(self, form):
        form.instance.author = self.request.user
        return super().form_valid(form)

class HealthTipDetailView(DetailView):
    model = HealthTip
    template_name = 'carelink/health_tip_detail.html'
    context_object_name = 'health_tip'

class HealthTipUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = HealthTip
    template_name = 'carelink/health_tip_form.html'
    fields = ['title', 'content', 'category', 'image', 'source']
    success_url = reverse_lazy('carelink:health_tips_list')

    def test_func(self):
        return self.request.user.is_staff

class HealthTipDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = HealthTip
    template_name = 'carelink/health_tip_confirm_delete.html'
    success_url = reverse_lazy('carelink:health_tips_list')

    def test_func(self):
        return self.request.user.is_staff

class HealthDocumentListView(LoginRequiredMixin, ListView):
    model = HealthDocument
    template_name = 'carelink/health_documents_list.html'
    context_object_name = 'health_documents'

    def get_queryset(self):
        user = self.request.user
        if user.user_type == 'CAREGIVER':
            return HealthDocument.objects.filter(
                Q(user=user) |
                Q(user__in=User.objects.filter(assigned_patients__in=user.assigned_patients.all()))
            ).distinct()
        else:  # FAMILY
            return HealthDocument.objects.filter(
                Q(user=user) |
                Q(user__in=User.objects.filter(patients__in=user.patients.all()))
            ).distinct()

class HealthDocumentCreateView(LoginRequiredMixin, CreateView):
    model = HealthDocument
    form_class = HealthDocumentForm
    template_name = 'carelink/health_document_form.html'
    success_url = reverse_lazy('carelink:health_document_list')

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)

class HealthDocumentDetailView(DetailView):
    model = HealthDocument
    template_name = 'carelink/health_document_detail.html'
    context_object_name = 'health_document'

class HealthDocumentUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = HealthDocument
    form_class = HealthDocumentForm
    template_name = 'carelink/health_document_form.html'
    success_url = reverse_lazy('carelink:health_document_list')

    def test_func(self):
        user = self.request.user
        document_user = self.get_object().user

        if user.user_type == 'CAREGIVER':
            patients = user.assigned_patients.all()
            family_members = User.objects.filter(patients__in=patients)
            return user == document_user or document_user in family_members
        elif user.user_type == 'FAMILY':
            patients = User.objects.filter(family_members=user)
            caregivers = User.objects.filter(assigned_patient__family_members=user)
            return user == document_user or document_user in patients or document_user in caregivers
        else:
            return user == document_user

class HealthDocumentDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = HealthDocument
    template_name = 'carelink/health_document_confirm_delete.html'
    success_url = reverse_lazy('carelink:health_document_list')

    def test_func(self):
        user = self.request.user
        document_user = self.get_object().user

        if user.user_type == 'CAREGIVER':
            patients = user.assigned_patients.all()
            family_members = User.objects.filter(patients__in=patients)
            return user == document_user or document_user in family_members
        elif user.user_type == 'FAMILY':
            patients = User.objects.filter(family_members=user)
            caregivers = User.objects.filter(assigned_patient__family_members=user)
            return user == document_user or document_user in patients or document_user in caregivers
        else:
            return user == document_user

class AboutUsView(TemplateView):
    template_name = 'carelink/about.html'

class ContactView(TemplateView):
    template_name = 'carelink/contact.html'

class PrivacyPolicyView(TemplateView):
    template_name = 'carelink/privacy_policy.html'

class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    model = User
    form_class = UserProfileUpdateForm
    template_name = 'carelink/profile_update_form.html'
    success_url = reverse_lazy('carelink:profile')

    def get_object(self, queryset=None):
        return self.request.user

    def form_valid(self, form):
        messages.success(self.request, 'Profile updated successfully.')
        return super().form_valid(form)

class MessagesView(LoginRequiredMixin, ListView):
    model = Communication
    template_name = 'carelink/messages.html'
    context_object_name = 'conversations'

    def get_queryset(self):
        user = self.request.user
        
        # Get all patients related to the user
        if user.user_type == 'CAREGIVER':
            patients = Patient.objects.filter(assigned_caregiver=user)
        else:  # FAMILY
            patients = Patient.objects.filter(family_members=user)
        
        # Get unique conversations for each patient
        conversations = []
        for patient in patients:
            if user.user_type == 'CAREGIVER':
                other_user = patient.family_members.first()
            else:  # FAMILY
                other_user = patient.assigned_caregiver
            
            if other_user:
                # Get latest message for this conversation
                latest_message = Communication.objects.filter(
                    Q(sender=user, receiver=other_user, patient=patient) |
                    Q(sender=other_user, receiver=user, patient=patient)
                ).order_by('-timestamp').first()
                
                if latest_message:
                    conversations.append({
                        'patient': patient,
                        'other_user': other_user,
                        'latest_message': latest_message,
                        'unread_count': Communication.objects.filter(
                            sender=other_user,
                            receiver=user,
                            patient=patient,
                            is_read=False
                        ).count()
                    })
        
        return sorted(conversations, key=lambda x: x['latest_message'].timestamp, reverse=True)

class ConversationView(LoginRequiredMixin, ListView):
    model = Communication
    template_name = 'carelink/conversation.html'
    context_object_name = 'messages'

    def get_queryset(self):
        user = self.request.user
        other_user_id = self.kwargs.get('user_id')
        patient_id = self.kwargs.get('patient_id')
        
        # Get all messages between these users for this patient
        messages = Communication.objects.filter(
            Q(sender=user, receiver_id=other_user_id, patient_id=patient_id) |
            Q(sender_id=other_user_id, receiver=user, patient_id=patient_id)
        ).order_by('timestamp')
        
        # Mark unread messages as read
        messages.filter(receiver=user, is_read=False).update(is_read=True)
        
        return messages

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        patient_id = self.kwargs.get('patient_id')
        other_user_id = self.kwargs.get('user_id')
        
        context['patient'] = get_object_or_404(Patient, id=patient_id)
        context['other_user'] = get_object_or_404(User, id=other_user_id)
        return context

class SendMessageView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        receiver_id = kwargs.get('receiver_id')
        patient_id = request.POST.get('patient_id')
        message_text = request.POST.get('message')
        
        if not all([receiver_id, patient_id, message_text]):
            messages.error(request, 'Missing required information')
            return redirect('carelink:messages')
        
        try:
            receiver = User.objects.get(id=receiver_id)
            patient = Patient.objects.get(id=patient_id)
            
            # Verify that both users are related to this patient
            is_valid = False
            if request.user.user_type == 'CAREGIVER':
                is_valid = (patient.assigned_caregiver == request.user and 
                          patient.family_members.filter(id=receiver.id).exists())
            else:  # FAMILY
                is_valid = (patient.family_members.filter(id=request.user.id).exists() and 
                          patient.assigned_caregiver == receiver)
            
            if not is_valid:
                messages.error(request, 'Invalid message recipient')
                return redirect('carelink:messages')
            
            # Create and save the message
            Communication.objects.create(
                sender=request.user,
                receiver=receiver,
                patient=patient,
                message=message_text
            )
            
            messages.success(request, 'Message sent successfully')
            return redirect('carelink:conversation', user_id=receiver_id, patient_id=patient_id)
            
        except (User.DoesNotExist, Patient.DoesNotExist):
            messages.error(request, 'Invalid user or patient')
            return redirect('carelink:messages')
    
class HealthDashboardView(LoginRequiredMixin, UserPassesTestMixin, View):
    template_name = 'carelink/health_dashboard.html'
    
    def test_func(self):
        return self.request.user.user_type in ['CAREGIVER', 'FAMILY']
    
    def get(self, request, patient_id, *args, **kwargs):
        patient = get_object_or_404(Patient, pk=patient_id)
        
        # Check if user has permission to view this patient
        if request.user.user_type == 'CAREGIVER':
            if not hasattr(request.user, 'assigned_patient') or request.user.assigned_patient != patient:
                raise PermissionDenied("You are not authorized to view this patient's dashboard.")
        elif request.user.user_type == 'FAMILY' and patient not in request.user.patients.all():
            raise PermissionDenied("You are not authorized to view this patient's dashboard.")
        
        context = self.get_context_data(patient=patient)
        return render(request, self.template_name, context)
    
    def get_context_data(self, **kwargs):
        context = {}
        patient = kwargs.get('patient')
        
        if patient:
            context['patient'] = patient
            context['page_title'] = f"Health Dashboard - {patient.first_name} {patient.last_name}"
            
            # Get the latest health log
            latest_health_log = HealthLog.objects.filter(patient=patient).order_by('-timestamp').first()
            context['latest_health_log'] = latest_health_log
            
            # Get health check schedule
            health_schedule = HealthCheckSchedule.objects.filter(patient=patient, is_active=True).first()
            context['health_schedule'] = health_schedule
            
            # Get recent tasks
            recent_tasks = Task.objects.filter(patient=patient).order_by('-created_at')[:5]
            context['recent_tasks'] = recent_tasks
            
            # Get active medications
            active_medications = Medication.objects.filter(patient=patient, end_date__gte=timezone.now().date()).order_by('start_date')
            context['active_medications'] = active_medications
        
        return context

class GenerateHealthReportView(View):
    def get(self, request, patient_id):
        try:
            from .models import Patient  # Keep direct model import

            patient = get_object_or_404(Patient, pk=patient_id)
            report_type = request.GET.get('type', 'DAILY').upper()
            
            analyzer = HealthAnalyzer(patient)
            report = analyzer.generate_report(report_type)
            
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{report_type.lower()}_health_report.pdf"'
            
            buffer = self._generate_pdf(report)
            response.write(buffer.getvalue())
            buffer.close()
            
            return response
        
        except Exception as e:
            logger.error("Report generation error: %s", e, exc_info=True)
            return HttpResponseServerError("Report generation failed: %s" % str(e))

    def _generate_pdf(self, report):
        buffer = BytesIO()
        
        try:
            doc = SimpleDocTemplate(buffer, pagesize=letter)
            styles = getSampleStyleSheet()
            story = []

            # Add report details
            story.append(Paragraph(f"{report.report_type} Health Report", styles['Title']))
            story.append(Spacer(1, 12))
            
            story.append(Paragraph(f"Patient: {report.patient.first_name} {report.patient.last_name}", styles['Normal']))
            story.append(Paragraph(f"Report Period: {report.report_period} days", styles['Normal']))
            story.append(Paragraph(f"Generated Date: {report.generated_date.strftime('%Y-%m-%d')}", styles['Normal']))
            story.append(Spacer(1, 12))

            # Parse report data safely
            try:
                report_data = json.loads(report.report_data) if report.report_data else {}
                
                for key, values in report_data.items():
                    story.append(Paragraph(f"{key.capitalize()} Data:", styles['Heading3']))
                    
                    # Filter out None values and convert to strings
                    filtered_values = [str(v) for v in values if v is not None]
                    value_str = ', '.join(filtered_values) if filtered_values else "No data available"
                    
                    story.append(Paragraph(value_str, styles['Normal']))
                    story.append(Spacer(1, 6))

            except Exception as data_error:
                logger.error("Report data parsing error: %s", data_error, exc_info=True)
                story.append(Paragraph("Error parsing report data", styles['Normal']))

            # Build PDF
            doc.build(story)
            
            buffer.seek(0)
            return buffer

        except Exception as e:
            logger.error("PDF generation error: %s", e, exc_info=True)
            raise HttpResponseServerError("PDF generation failed: %s" % str(e))
    

class HealthTipListView(LoginRequiredMixin, ListView):
    model = HealthTip
    template_name = 'carelink/health_tips_list.html'
    context_object_name = 'health_tips'

class HealthTipCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = HealthTip
    template_name = 'carelink/health_tip_form.html'
    fields = ['title', 'content', 'category', 'image', 'source']
    success_url = reverse_lazy('carelink:health_tips_list')

    def test_func(self):
        return self.request.user.is_staff

    def form_valid(self, form):
        form.instance.author = self.request.user
        return super().form_valid(form)

class HealthTipDetailView(LoginRequiredMixin, DetailView):
    model = HealthTip
    template_name = 'carelink/health_tip_detail.html'
    context_object_name = 'tip'

class HealthTipUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = HealthTip
    template_name = 'carelink/health_tip_form.html'
    fields = ['title', 'content', 'category', 'image', 'source']
    success_url = reverse_lazy('carelink:health_tips_list')

    def test_func(self):
        return self.request.user.is_staff

class HealthTipDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = HealthTip
    template_name = 'carelink/health_tip_confirm_delete.html'
    success_url = reverse_lazy('carelink:health_tips_list')

    def test_func(self):
        return self.request.user.is_staff

class HealthDocumentListView(LoginRequiredMixin, ListView):
    model = HealthDocument
    template_name = 'carelink/health_documents_list.html'
    context_object_name = 'documents'
    ordering = ['-uploaded_at']

    def get_queryset(self):
        user = self.request.user
        if user.user_type == 'CAREGIVER':
            # Caregiver can see their own documents and documents of their assigned patients' family members
            patients = user.assigned_patient
            family_members = User.objects.filter(patients__in=[patients])
            return HealthDocument.objects.filter(Q(user=user) | Q(user__in=family_members))
        elif user.user_type == 'FAMILY':
            # Family members can see their own documents and documents of their assigned caregivers
            caregivers = User.objects.filter(assigned_patient__family_members=user)
            patients = User.objects.filter(family_members=user)
            return HealthDocument.objects.filter(Q(user=user) | Q(user__in=caregivers) | Q(user__in=patients))
        else:
            # Admins can see all documents
            return HealthDocument.objects.all()

class HealthDocumentCreateView(LoginRequiredMixin, CreateView):
    model = HealthDocument
    form_class = HealthDocumentForm
    template_name = 'carelink/health_document_form.html'
    success_url = reverse_lazy('carelink:health_document_list')

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)

class HealthDocumentDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    model = HealthDocument
    template_name = 'carelink/health_document_detail.html'
    context_object_name = 'document'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        document = self.object.document
        try:
            with document.open('rb') as file:
                reader = PdfReader(file)
                text = ''
                for page in reader.pages:
                    text += page.extract_text()
            context['document_text'] = text
        except Exception as e:
            context['document_text'] = None
            # Optionally log the error
        return context

    def test_func(self):
        user = self.request.user
        document_user = self.get_object().user

        if user.user_type == 'CAREGIVER':
            patients = user.assigned_patient
            family_members = User.objects.filter(patients__in=[patients])
            return user == document_user or document_user in family_members
        elif user.user_type == 'FAMILY':
            patients = User.objects.filter(family_members=user)
            caregivers = User.objects.filter(assigned_patient__family_members=user)
            return user == document_user or document_user in patients or document_user in caregivers
        else:
            return user == document_user

class HealthDocumentUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = HealthDocument
    form_class = HealthDocumentForm
    template_name = 'carelink/health_document_form.html'
    success_url = reverse_lazy('carelink:health_document_list')

    def test_func(self):
        user = self.request.user
        document_user = self.get_object().user

        if user.user_type == 'CAREGIVER':
            patients = user.assigned_patient
            family_members = User.objects.filter(patients__in=[patients])
            return user == document_user or document_user in family_members
        elif user.user_type == 'FAMILY':
            patients = User.objects.filter(family_members=user)
            caregivers = User.objects.filter(assigned_patient__family_members=user)
            return user == document_user or document_user in patients or document_user in caregivers
        else:
            return user == document_user

class HealthDocumentDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = HealthDocument
    template_name = 'carelink/health_document_confirm_delete.html'
    success_url = reverse_lazy('carelink:health_document_list')

    def test_func(self):
        user = self.request.user
        document_user = self.get_object().user

        if user.user_type == 'CAREGIVER':
            patients = user.assigned_patient
            family_members = User.objects.filter(patients__in=[patients])
            return user == document_user or document_user in family_members
        elif user.user_type == 'FAMILY':
            patients = User.objects.filter(family_members=user)
            caregivers = User.objects.filter(assigned_patient__family_members=user)
            return user == document_user or document_user in patients or document_user in caregivers
        else:
            return user == document_user

class TaskListView(LoginRequiredMixin, ListView):
    model = Task
    template_name = 'carelink/task_list.html'
    context_object_name = 'tasks'
    
    def get_queryset(self):
        if self.request.user.user_type == 'CAREGIVER':
            return Task.objects.filter(caregiver=self.request.user).order_by('-created_at')
        else:
            # For family members, show tasks related to their patients
            return Task.objects.filter(patient__family_member=self.request.user).order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        queryset = self.get_queryset()
        context['pending_tasks'] = queryset.filter(status='PENDING')
        context['pending_review_tasks'] = queryset.filter(status='PENDING_REVIEW')
        context['completed_tasks'] = queryset.filter(status='COMPLETED')
        return context

class CareRequestListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = CareRequest
    template_name = 'carelink/care_request_list.html'
    context_object_name = 'care_requests'
    
    def test_func(self):
        # Only allow admins and family members
        return self.request.user.is_staff or self.request.user.user_type == 'FAMILY'
    
    def get_queryset(self):
        if self.request.user.is_staff:
            # Admins see all pending requests
            return CareRequest.objects.filter(status='PENDING').order_by('-request_date')
        else:
            # Family members only see their own requests
            return CareRequest.objects.filter(user=self.request.user).order_by('-request_date')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.is_staff:
            # For admins, categorize by status
            context['pending_requests'] = self.get_queryset()
            context['approved_requests'] = CareRequest.objects.filter(status='APPROVED')
            context['rejected_requests'] = CareRequest.objects.filter(status='REJECTED')
        else:
            # For family members, show their requests by status
            context['pending_requests'] = self.get_queryset().filter(status='PENDING')
            context['approved_requests'] = self.get_queryset().filter(status='APPROVED')
            context['rejected_requests'] = self.get_queryset().filter(status='REJECTED')
            context['patients'] = Patient.objects.filter(family_members=self.request.user)
        
        return context

@login_required
@staff_member_required  # Only admins can access this view
def approve_care_request(request, request_id):
    care_request = get_object_or_404(CareRequest, id=request_id)
    
    if request.method == 'POST':
        caregiver_id = request.POST.get('caregiver')
        caregiver = get_object_or_404(User, id=caregiver_id)
        
        # Validate caregiver availability using the new OneToOne relationship
        try:
            if hasattr(caregiver, 'assigned_patient'):
                messages.error(request, f'This caregiver is already assigned to patient {caregiver.assigned_patient}')
                return redirect('carelink:admin_dashboard')
        except User.assigned_patient.RelatedObjectDoesNotExist:
            pass  # This is good - means the caregiver has no assigned patient
        
        # Update care request
        care_request.status = 'APPROVED'
        care_request.caregiver = caregiver
        care_request.save()
        
        if care_request.request_type == 'NEW_PATIENT':
            # Create new patient for new patient requests
            try:
                patient = Patient.objects.create(
                    first_name=care_request.patient_name,
                    last_name=care_request.patient_last_name,
                    date_of_birth=care_request.patient_date_of_birth,
                    medical_condition=care_request.patient_condition,
                    emergency_contact=care_request.emergency_contact,
                    address=care_request.patient_address,
                    assigned_caregiver=caregiver
                )
                patient.family_members.add(care_request.user)
                
                # Create initial health check schedule
                HealthCheckSchedule.objects.create(
                    patient=patient,
                    caregiver=caregiver,
                    next_check=timezone.now() + timedelta(hours=6)
                )
                
                messages.success(request, 'Care request approved and patient assigned successfully.')
            except Exception as e:
                messages.error(request, f'Failed to create patient: {str(e)}')
                return redirect('carelink:admin_dashboard')
        else:
            # Handle service request approval
            try:
                # Create task for the caregiver
                Task.objects.create(
                    caregiver=caregiver,
                    patient=care_request.patient,
                    title=f'Service Request: {care_request.service_type}',
                    description=care_request.notes,
                    due_date=care_request.requested_date,
                    status='PENDING'
                )
                messages.success(request, 'Service request approved and task created for caregiver.')
            except Exception as e:
                messages.error(request, f'Failed to create task: {str(e)}')
                return redirect('carelink:admin_dashboard')
        
        # Create notification for the caregiver
        Notification.objects.create(
            user=caregiver,
            type='SYSTEM',
            title='New Patient Assignment',
            message=f'You have been assigned to a new patient: {care_request.patient_name}'
        )
        
        return redirect('carelink:admin_dashboard')
    
    # GET request - show approval form
    # Only show caregivers who don't have an assigned patient
    available_caregivers = User.objects.filter(
        user_type='CAREGIVER'
    ).exclude(
        assigned_patient__isnull=False
    )
    
    return render(request, 'carelink/approve_care_request.html', {
        'care_request': care_request,
        'caregivers': available_caregivers
    })

@login_required
@staff_member_required  # Only admins can access this view
def reject_care_request(request, request_id):
    care_request = get_object_or_404(CareRequest, id=request_id)
    care_request.status = 'REJECTED'
    care_request.save()
    messages.success(request, 'Care request rejected.')
    return redirect('carelink:admin_dashboard')

from django.contrib.auth.views import PasswordResetView, PasswordResetDoneView, PasswordResetConfirmView, PasswordResetCompleteView
from django.urls import reverse_lazy
from django.contrib.auth.forms import PasswordResetForm

# Custom Password Reset View
class CustomPasswordResetView(PasswordResetView):
    template_name = 'registration/password_reset_form.html'
    email_template_name = 'registration/password_reset_email.html'
    html_email_template_name = 'registration/password_reset_email.html'
    subject_template_name = 'registration/password_reset_subject.txt'
    success_url = reverse_lazy('carelink:password_reset_done')
    
    def send_mail(self, subject_template_name, email_template_name,
                 context, from_email, to_email, html_email_template_name=None):
        """Send a django.core.mail.EmailMultiAlternatives instead of EmailMessage"""
        subject = loader.render_to_string(subject_template_name, context)
        subject = ''.join(subject.splitlines())
        
        # Create plain text version
        text_content = loader.render_to_string(email_template_name, context)
        
        # Create HTML version
        html_content = loader.render_to_string(html_email_template_name, context)
        
        # Create the email message
        email_message = EmailMultiAlternatives(
            subject=subject,
            body=text_content,  # Plain text version as body
            from_email=from_email,
            to=[to_email]
        )
        
        # Attach HTML version
        email_message.attach_alternative(html_content, 'text/html')
        
        email_message.send()

    def form_valid(self, form):
        """Override form_valid to ensure HTML emails are sent."""
        opts = {
            'use_https': self.request.is_secure(),
            'token_generator': self.token_generator,
            'from_email': settings.DEFAULT_FROM_EMAIL,
            'email_template_name': self.email_template_name,
            'subject_template_name': self.subject_template_name,
            'request': self.request,
            'html_email_template_name': self.html_email_template_name,
            'extra_email_context': {
                'protocol': 'https' if self.request.is_secure() else 'http',
                'domain': self.request.get_host(),
                'site_name': 'CareLink',
            }
        }
        form.save(**opts)
        return super().form_valid(form)

# Custom Password Reset Done View
class CustomPasswordResetDoneView(PasswordResetDoneView):
    template_name = 'registration/password_reset_done.html'

# Custom Password Reset Confirm View
class CustomPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = 'registration/password_reset_confirm.html'
    success_url = reverse_lazy('carelink:password_reset_complete')

# Custom Password Reset Complete View
class CustomPasswordResetCompleteView(PasswordResetCompleteView):
    template_name = 'registration/password_reset_complete.html'


from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

def assign_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    task.assigned_to = request.user
    task.save()
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        'notifications',
        {
            'type': 'send_notification',
            'message': f'You have been assigned a new task: {task.title}'
        }
    )
    return redirect('task_detail', task_id=task_id)

from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.contrib import messages
from django.views.generic import ListView, CreateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import Medication, MedicationSchedule
from .forms import MedicationForm, MedicationScheduleFormSet

class MedicationListView(LoginRequiredMixin, ListView):
    model = Medication
    template_name = 'carelink/medication_list.html'
    context_object_name = 'medications'

    def get_queryset(self):
        if self.request.user.user_type == 'CAREGIVER':
            return Medication.objects.filter(
                patient__assigned_caregiver=self.request.user,
                status='ACTIVE'
            )
        elif self.request.user.user_type == 'FAMILY':
            return Medication.objects.filter(
                patient__family_members=self.request.user,
                status='ACTIVE'
            )
        return Medication.objects.none()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['upcoming_doses'] = MedicationSchedule.objects.filter(
            medication__in=self.get_queryset()
        ).order_by('scheduled_time')
        context['needs_refill'] = self.get_queryset().filter(
            refills_remaining__lte=1
        )
        return context

class MedicationCreateView(LoginRequiredMixin, CreateView):
    model = Medication
    form_class = MedicationForm
    template_name = 'carelink/medication_form.html'
    success_url = reverse_lazy('carelink:medication_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['schedule_formset'] = MedicationScheduleFormSet(
                self.request.POST
            )
        else:
            context['schedule_formset'] = MedicationScheduleFormSet()
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        schedule_formset = context['schedule_formset']
        if schedule_formset.is_valid():
            self.object = form.save(commit=False)
            self.object.created_by = self.request.user
            self.object.save()
            
            schedule_formset.instance = self.object
            schedule_formset.save()
            
            # Create initial reminders
            self._create_reminders(self.object)
            
            messages.success(self.request, 'Medication added successfully.')
            return redirect(self.get_success_url())
        else:
            return self.render_to_response(self.get_context_data(form=form))

    def _create_reminders(self, medication):
        schedules = medication.schedules.all()
        for schedule in schedules:
            reminder_time = timezone.now().replace(
                hour=schedule.scheduled_time.hour,
                minute=schedule.scheduled_time.minute,
                second=0
            )
            
            # Create upcoming dose reminder
            MedicationReminder.objects.create(
                medication=medication,
                schedule=schedule,
                reminder_time=reminder_time - timedelta(minutes=30),
                reminder_type='UPCOMING'
            )
            
            # Create refill reminder if needed
            if medication.refills_remaining <= 1 and medication.next_refill_date:
                MedicationReminder.objects.create(
                    medication=medication,
                    schedule=schedule,
                    reminder_time=medication.next_refill_date - timedelta(days=3),
                    reminder_type='REFILL'
                )

class MedicationDetailView(LoginRequiredMixin, DetailView):
    model = Medication
    template_name = 'carelink/medication_detail.html'
    context_object_name = 'medication'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['schedules'] = self.object.schedules.all()
        context['logs'] = self.object.logs.all().order_by('-taken_at')[:10]
        context['interactions'] = MedicationInteraction.objects.filter(
            Q(medication1=self.object) | Q(medication2=self.object)
        )
        return context

class AddMedicationView(LoginRequiredMixin, CreateView):
    model = Medication
    form_class = MedicationForm
    template_name = 'carelink/patient_detail.html'
    
    def form_valid(self, form):
        form.instance.patient_id = self.kwargs['pk']
        form.instance.created_by = self.request.user
        form.instance.status = 'ACTIVE'
        response = super().form_valid(form)
        
        # Create medication schedule based on frequency
        if form.instance.frequency == 'DAILY':
            MedicationSchedule.objects.create(
                medication=form.instance,
                scheduled_time=datetime.strptime('09:00', '%H:%M').time(),
                dosage_amount=form.instance.dosage
            )
        elif form.instance.frequency == 'TWICE_DAILY':
            MedicationSchedule.objects.create(
                medication=form.instance,
                scheduled_time=datetime.strptime('09:00', '%H:%M').time(),
                dosage_amount=form.instance.dosage
            )
            MedicationSchedule.objects.create(
                medication=form.instance,
                scheduled_time=datetime.strptime('21:00', '%H:%M').time(),
                dosage_amount=form.instance.dosage
            )
        elif form.instance.frequency == 'THREE_TIMES_DAILY':
            times = ['09:00', '14:00', '21:00']
            for time_str in times:
                MedicationSchedule.objects.create(
                    medication=form.instance,
                    scheduled_time=datetime.strptime(time_str, '%H:%M').time(),
                    dosage_amount=form.instance.dosage
                )
        elif form.instance.frequency == 'FOUR_TIMES_DAILY':
            times = ['09:00', '13:00', '17:00', '21:00']
            for time_str in times:
                MedicationSchedule.objects.create(
                    medication=form.instance,
                    scheduled_time=datetime.strptime(time_str, '%H:%M').time(),
                    dosage_amount=form.instance.dosage
                )
        
        messages.success(self.request, 'Medication added successfully.')
        return response
    
    def get_success_url(self):
        return reverse('carelink:patient_detail', kwargs={'pk': self.kwargs['pk']})

class ProfileView(LoginRequiredMixin, DetailView):
    model = User
    template_name = 'carelink/profile.html'
    context_object_name = 'user'

    def get_object(self, queryset=None):
        return self.request.user

class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    model = User
    template_name = 'carelink/profile_update_form.html'
    form_class = UserProfileUpdateForm
    success_url = reverse_lazy('carelink:profile')

    def get_object(self):
        return self.request.user

    def form_valid(self, form):
        messages.success(self.request, 'Your profile has been updated successfully.')
        return super().form_valid(form)

class NotificationsView(LoginRequiredMixin, ListView):
    model = Notification
    template_name = 'carelink/notifications.html'
    context_object_name = 'notifications'

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by('-created_at')

    def get(self, request, *args, **kwargs):
        # Mark all unread notifications as read when viewing
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return super().get(request, *args, **kwargs)

class AboutUsView(TemplateView):
    template_name = 'carelink/about.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'About Us'
        return context

class ContactView(TemplateView):
    template_name = 'carelink/contact.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Contact Us'
        return context

    def post(self, request, *args, **kwargs):
        name = request.POST.get('name')
        email = request.POST.get('email')
        subject = request.POST.get('subject')
        message = request.POST.get('message')

        # Send email
        email_subject = f'Contact Form: {subject}'
        email_message = f'From: {name}\nEmail: {email}\n\nMessage:\n{message}'
        try:
            send_mail(
                email_subject,
                email_message,
                settings.DEFAULT_FROM_EMAIL,
                [settings.CONTACT_EMAIL],
                fail_silently=False,
            )
            messages.success(request, 'Thank you for contacting us! We will get back to you soon.')
        except Exception as e:
            messages.error(request, 'Sorry, there was an error sending your message. Please try again later.')

        return redirect('carelink:contact')

class PrivacyPolicyView(TemplateView):
    template_name = 'carelink/privacy_policy.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Privacy Policy'
        context['last_updated'] = 'March 2, 2024'
        return context

@login_required
@require_http_methods(['POST'])
def mark_recommendation_addressed(request, rec_id):
    try:
        recommendation = MLRecommendation.objects.get(id=rec_id)
        
        # Check if user has permission to mark this recommendation
        if request.user.user_type in ['CAREGIVER', 'FAMILY']:
            if request.user.user_type == 'CAREGIVER' and recommendation.patient.assigned_caregiver == request.user:
                recommendation.is_addressed = True
                recommendation.addressed_at = timezone.now()
                recommendation.addressed_by = request.user
                recommendation.save()
                return JsonResponse({'success': True})
            elif request.user.user_type == 'FAMILY' and request.user in recommendation.patient.family_members.all():
                recommendation.is_addressed = True
                recommendation.addressed_at = timezone.now()
                recommendation.addressed_by = request.user
                recommendation.save()
                return JsonResponse({'success': True})
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)
    except MLRecommendation.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Recommendation not found'}, status=404)

@login_required
@require_http_methods(['GET'])
def get_ai_recommendations(request, patient_id):
    try:
        patient = get_object_or_404(Patient, pk=patient_id)
        logger.info("Processing recommendations for patient %s", patient_id)
        
        if request.user.user_type == 'CAREGIVER':
            if not hasattr(request.user, 'assigned_patient') or request.user.assigned_patient != patient:
                logger.warning("Unauthorized caregiver access attempt for patient %s", patient_id)
                return JsonResponse({
                    'success': False,
                    'message': 'You are not authorized to view this patient\'s recommendations.'
                })
        elif request.user.user_type == 'FAMILY' and patient not in request.user.patients.all():
            logger.warning("Unauthorized family member access attempt for patient %s", patient_id)
            return JsonResponse({
                'success': False,
                'message': 'You are not authorized to view this patient\'s recommendations.'
            })
            
        latest_health_log = HealthLog.objects.filter(patient=patient).order_by('-timestamp').first()
        logger.info("Latest health log found: %s", latest_health_log is not None)
        
        if not latest_health_log:
            return JsonResponse({
                'success': False,
                'error': 'No health logs found for this patient'
            }, status=404)
        
        # Prepare data for Gemini API
        prompt = {
            "contents": [{
                "parts": [{
                    "text": """You are a medical recommendation system. Based on the following patient health data, generate 3-5 medical recommendations. You must respond ONLY with a valid JSON array. Do not include any other text, explanations, or formatting.

Latest Health Data:
- Temperature: {} °C
- Blood Pressure: {} mmHg
- Pulse Rate: {} bpm
- Oxygen Level: {}%
- Notes: {}

Required format:
[{{"title": "First Recommendation", "description": "Details..."}}, {{"title": "Second Recommendation", "description": "Details..."}}]""".format(
                        float(latest_health_log.temperature) if latest_health_log.temperature is not None else 'Not recorded',
                        latest_health_log.blood_pressure if latest_health_log.blood_pressure else 'Not recorded',
                        latest_health_log.pulse_rate if latest_health_log.pulse_rate else 'Not recorded',
                        latest_health_log.oxygen_level if latest_health_log.oxygen_level else 'Not recorded',
                        latest_health_log.notes if latest_health_log.notes else 'No additional notes'
                    )
                }]
            }]
        }
        
        # Call Gemini API
        api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
        api_key = settings.GEMINI_API_KEY
        
        logger.info("Checking Gemini API configuration")
        if not api_key:
            logger.error("Gemini API key not configured")
            return JsonResponse({
                'success': False,
                'error': 'AI service key not configured'
            }, status=500)
        
        logger.info("Making request to Gemini API")
        try:
            response = requests.post(
                f"{api_url}?key={api_key}",
                json=prompt,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            if response.status_code != 200:
                error_msg = response.text if response.text else 'Unknown error'
                logger.error("AI service error: %s - %s", response.status_code, error_msg)
                return JsonResponse({
                    'success': False,
                    'error': 'Failed to get recommendations: ' + error_msg
                }, status=500)
            
            logger.info("Parsing Gemini API response")
            response_data = response.json()
            
            if not response_data.get('candidates'):
                logger.error("Invalid API response format: %s", response_data)
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid response from AI service'
                }, status=500)
            
            text_response = response_data['candidates'][0]['content']['parts'][0]['text'].strip()
            logger.info("Raw text response: %s", text_response)
            
            try:
                # Try to clean up the response text to ensure it's valid JSON
                text_response = text_response.strip()
                if not text_response.startswith('['):
                    # Find the first [ and last ]
                    start = text_response.find('[')
                    end = text_response.rfind(']')
                    if start != -1 and end != -1:
                        text_response = text_response[start:end + 1]
                    else:
                        raise json.JSONDecodeError("No JSON array found in response", text_response, 0)
                
                recommendations = json.loads(text_response)
                
                if not isinstance(recommendations, list):
                    logger.error("Parsed JSON is not a list: %s", recommendations)
                    return JsonResponse({
                        'success': False,
                        'error': 'Invalid recommendations format'
                    }, status=500)
                
                formatted_recommendations = []
                for rec in recommendations:
                    if isinstance(rec, dict) and 'title' in rec and 'description' in rec:
                        formatted_recommendations.append({
                            'title': str(rec['title']).strip(),
                            'description': str(rec['description']).strip()
                        })
                
                if not formatted_recommendations:
                    logger.error("No valid recommendations found in parsed JSON")
                    return JsonResponse({
                        'success': False,
                        'error': 'No valid recommendations found'
                    }, status=500)
                
                logger.info("Successfully generated %d recommendations", len(formatted_recommendations))
                return JsonResponse({
                    'success': True,
                    'recommendations': formatted_recommendations,
                    'patient_name': f"{patient.first_name} {patient.last_name}",
                    'generated_at': timezone.now().isoformat()
                })
                
            except json.JSONDecodeError as e:
                logger.error("JSON parsing error: %s. Raw response: %s", str(e), text_response)
                return JsonResponse({
                    'success': False,
                    'error': 'Failed to parse recommendations: ' + str(e)
                }, status=500)
                
        except requests.RequestException as e:
            logger.error("API request error: %s", str(e))
            return JsonResponse({
                'success': False,
                'error': 'Failed to connect to AI service: ' + str(e)
            }, status=500)
            
    except Exception as e:
        logger.error("Error in get_ai_recommendations: %s", str(e), exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'An unexpected error occurred: ' + str(e)
        }, status=500)

@login_required
def recommendations_view(request):
    """View function for displaying the recommendations page."""
    from django.contrib import messages
    from django.shortcuts import render, redirect, get_object_or_404
    # Get the first patient associated with the user
    patient = None
    if request.user.user_type == 'CAREGIVER':
        patient = request.user.assigned_patient
    elif request.user.user_type == 'FAMILY':
        patient = request.user.patients.first()
    
    if not patient:
        messages.error(request, 'No patient found. Please make sure you have an assigned patient.')
        return redirect('carelink:home')
    
    context = {
        'patient': patient,
        'page_title': f"Health Recommendations - {patient.first_name} {patient.last_name}"
    }
    return render(request, 'carelink/health_dashboard.html', context)

@login_required
@require_http_methods(['GET'])
def get_patient_next_appointment(request, patient_id):
    try:
        patient = get_object_or_404(Patient, pk=patient_id)
        # Get next appointment from health check schedule
        next_appointment = HealthCheckSchedule.objects.filter(
            patient=patient,
            next_check__gte=timezone.now()
        ).order_by('next_check').first()
        
        return JsonResponse({
            'appointment': next_appointment.next_check.isoformat() if next_appointment else None
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@require_http_methods(['GET'])
def get_patient_medication_adherence(request, patient_id):
    try:
        patient = get_object_or_404(Patient, pk=patient_id)
        # Calculate medication adherence based on medication logs
        end_date = timezone.now()
        start_date = end_date - timedelta(days=30)
        
        # Get all active medications for the patient
        active_medications = Medication.objects.filter(
            patient=patient,
            status='ACTIVE'
        ).prefetch_related('schedules', 'logs')
        
        total_scheduled_doses = 0
        total_taken_doses = 0
        
        for medication in active_medications:
            # Count scheduled doses
            daily_doses = medication.schedules.count()
            days_active = min(30, (end_date.date() - medication.start_date).days + 1)
            if days_active > 0:  # Only count if medication was active in the period
                total_scheduled_doses += daily_doses * days_active
            
            # Count taken doses
            taken_doses = medication.logs.filter(
                status='TAKEN',
                taken_at__range=(start_date, end_date)
            ).count()
            total_taken_doses += taken_doses
        
        # Calculate adherence rate
        adherence_rate = round((total_taken_doses / total_scheduled_doses * 100) if total_scheduled_doses > 0 else 100)
        
        return JsonResponse({
            'adherence_rate': adherence_rate
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@require_http_methods(['GET'])
def get_patient_alerts(request, patient_id):
    try:
        patient = get_object_or_404(Patient, pk=patient_id)
        # Get active alerts
        alerts = Notification.objects.filter(
            user__in=[patient.assigned_caregiver, *patient.family_members.all()],
            is_read=False,
            created_at__gte=timezone.now() - timedelta(days=7)
        ).count()
        
        return JsonResponse({
            'alert_count': alerts
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@require_http_methods(['GET'])
def get_patient_task_progress(request, patient_id):
    try:
        patient = get_object_or_404(Patient, pk=patient_id)
        # Calculate task completion rate
        total_tasks = Task.objects.filter(
            patient=patient,
            due_date__gte=timezone.now() - timedelta(days=30)
        ).count()
        
        completed_tasks = Task.objects.filter(
            patient=patient,
            due_date__gte=timezone.now() - timedelta(days=30),
            status='COMPLETED'
        ).count()
        
        completion_rate = round((completed_tasks / total_tasks * 100) if total_tasks > 0 else 0)
        
        return JsonResponse({
            'completion_rate': completion_rate
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@require_http_methods(['POST'])
def mark_task_for_review(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    
    # Ensure only the assigned caregiver can mark for review
    if request.user != task.caregiver:
        return JsonResponse({'success': False, 'error': 'You are not assigned to this task'}, status=403)
    
    try:
        task.mark_for_review()
        # Create notification for admin
        Notification.objects.create(
            user=User.objects.filter(is_staff=True).first(),
            type='TASK',
            title='Task Review Required',
            message=f'Task "{task.title}" needs review for completion'
        )
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

@login_required
@require_http_methods(['POST'])
def approve_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    
    # Ensure only staff members can approve tasks
    if not request.user.is_staff:
        return JsonResponse({'success': False, 'error': 'Only staff members can approve tasks'}, status=403)
    
    try:
        task.approve_completion(request.user)
        # Create notification for caregiver
        Notification.objects.create(
            user=task.caregiver,
            type='TASK',
            title='Task Approved',
            message=f'Your task "{task.title}" has been approved and marked as completed'
        )
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

@login_required
@require_http_methods(['GET'])
def get_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    
    # Ensure only the assigned caregiver or staff can view task details
    if request.user != task.caregiver and not request.user.is_staff:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    data = {
        'title': task.title,
        'description': task.description,
        'category': task.category,
        'priority': task.priority,
        'due_date': task.due_date.strftime('%Y-%m-%dT%H:%M'),
        'status': task.status
    }
    return JsonResponse(data)

@login_required
@require_http_methods(['POST'])
def edit_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    
    # Ensure only the assigned caregiver or staff can edit task
    if request.user != task.caregiver and not request.user.is_staff:
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
    
    try:
        data = json.loads(request.body)
        task.title = data.get('title', task.title)
        task.description = data.get('description', task.description)
        task.category = data.get('category', task.category)
        task.priority = data.get('priority', task.priority)
        task.due_date = datetime.strptime(data.get('due_date'), '%Y-%m-%dT%H:%M')
        task.save()
        
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

@login_required
@require_http_methods(['POST'])
def delete_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    
    # Ensure only the assigned caregiver or staff can delete task
    if request.user != task.caregiver and not request.user.is_staff:
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
    
    try:
        task.delete()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

@login_required
@require_http_methods(['GET'])
def get_vitals_data(request, patient_id):
    """Get vital signs data for the patient over a specified period."""
    try:
        patient = get_object_or_404(Patient, id=patient_id)
        period = request.GET.get('period', 'week')
        
        # Calculate date range
        end_date = timezone.now()
        if period == 'week':
            start_date = end_date - timedelta(days=7)
        else:  # month
            start_date = end_date - timedelta(days=30)
        
        # Get health logs for the period
        health_logs = HealthLog.objects.filter(
            patient=patient,
            timestamp__range=(start_date, end_date)
        ).order_by('timestamp')
        
        # Prepare data for chart
        labels = []
        bp_data = []
        temp_data = []
        
        for log in health_logs:
            labels.append(log.timestamp.strftime('%Y-%m-%d %H:%M'))
            
            # Process blood pressure (assuming format like "120/80")
            if log.blood_pressure:
                try:
                    systolic = int(log.blood_pressure.split('/')[0])
                    bp_data.append(systolic)
                except (ValueError, IndexError):
                    bp_data.append(None)
            else:
                bp_data.append(None)
            
            # Process temperature
            temp_data.append(float(log.temperature) if log.temperature else None)
        
        return JsonResponse({
            'success': True,
            'labels': labels,
            'bp_data': bp_data,
            'temp_data': temp_data
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@login_required
@require_http_methods(['POST'])
def add_medication(request, patient_id):
    """Add a new medication for the patient."""
    try:
        patient = get_object_or_404(Patient, id=patient_id)
        
        # Create new medication
        medication = Medication.objects.create(
            patient=patient,
            name=request.POST['name'],
            dosage=request.POST['dosage'],
            frequency=request.POST['frequency'],
            start_date=request.POST['start_date'],
            created_by=request.user
        )
        
        # Create medication schedule based on frequency
        if medication.frequency == 'daily':
            MedicationSchedule.objects.create(
                medication=medication,
                scheduled_time=datetime.strptime('09:00', '%H:%M').time(),
                dosage_amount=medication.dosage
            )
        elif medication.frequency == 'twice_daily':
            MedicationSchedule.objects.create(
                medication=medication,
                scheduled_time=datetime.strptime('09:00', '%H:%M').time(),
                dosage_amount=medication.dosage
            )
            MedicationSchedule.objects.create(
                medication=medication,
                scheduled_time=datetime.strptime('21:00', '%H:%M').time(),
                dosage_amount=medication.dosage
            )
        
        return JsonResponse({
            'success': True,
            'message': 'Medication added successfully'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@login_required
@require_http_methods(['POST'])
def mark_medication_taken(request):
    """Mark a medication as taken."""
    try:
        data = json.loads(request.body)
        medication_id = data.get('medication_id')
        medication = get_object_or_404(Medication, id=medication_id)
        
        # Create medication log
        MedicationLog.objects.create(
            medication=medication,
            status='TAKEN',
            taken_at=timezone.now()
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Medication marked as taken'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@login_required
@require_http_methods(['GET'])
def get_health_metrics(request, patient_id):
    """Get health metrics for the patient."""
    try:
        patient = get_object_or_404(Patient, id=patient_id)
        end_date = timezone.now()
        start_date = end_date - timedelta(days=30)
        
        # Get health logs for the last 30 days
        health_logs = HealthLog.objects.filter(
            patient=patient,
            timestamp__range=(start_date, end_date)
        )
        
        # Calculate blood pressure stability
        bp_readings = []
        for log in health_logs:
            if log.blood_pressure:
                try:
                    systolic = int(log.blood_pressure.split('/')[0])
                    bp_readings.append(systolic)
                except (ValueError, IndexError):
                    continue
        
        bp_stability = 100
        if bp_readings:
            avg_bp = sum(bp_readings) / len(bp_readings)
            variations = [abs(bp - avg_bp) for bp in bp_readings]
            max_variation = max(variations) if variations else 0
            bp_stability = max(0, 100 - (max_variation / 2))
        
        # Calculate temperature stability
        temp_readings = [float(log.temperature) for log in health_logs if log.temperature]
        temp_stability = 100
        if temp_readings:
            avg_temp = sum(temp_readings) / len(temp_readings)
            variations = [abs(temp - avg_temp) for temp in temp_readings]
            max_variation = max(variations) if variations else 0
            temp_stability = max(0, 100 - (max_variation * 10))
        
        # Calculate overall health score
        overall_score = (bp_stability + temp_stability) / 2
        
        return JsonResponse({
            'success': True,
            'bp_stability': round(bp_stability, 1),
            'temp_stability': round(temp_stability, 1),
            'overall_score': round(overall_score, 1)
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@login_required
@require_http_methods(['GET'])
def get_recent_activities(request, patient_id):
    """Get recent health-related activities for the patient."""
    try:
        patient = get_object_or_404(Patient, id=patient_id)
        end_date = timezone.now()
        start_date = end_date - timedelta(days=7)
        
        # Get recent health logs
        health_logs = HealthLog.objects.filter(
            patient=patient,
            timestamp__range=(start_date, end_date)
        ).order_by('-timestamp')[:5]
        
        # Get recent medication logs
        med_logs = MedicationLog.objects.filter(
            medication__patient=patient,
            taken_at__range=(start_date, end_date)
        ).order_by('-taken_at')[:5]
        
        # Combine and format activities
        activities = []
        
        for log in health_logs:
            activities.append({
                'title': 'Health Check Recorded',
                'timestamp': log.timestamp.isoformat(),
                'details': f"Temperature: {log.temperature}°C, BP: {log.blood_pressure}"
            })
        
        for log in med_logs:
            activities.append({
                'title': f"Medication: {log.medication.name}",
                'timestamp': log.taken_at.isoformat(),
                'details': f"Status: {log.status}"
            })
        
        # Sort activities by timestamp
        activities.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return JsonResponse({
            'success': True,
            'activities': activities[:10]  # Return most recent 10 activities
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@login_required
@require_http_methods(['POST'])
def mark_notification_read(request, notification_id):
    """Mark a single notification as read."""
    try:
        notification = get_object_or_404(Notification, id=notification_id, user=request.user)
        notification.is_read = True
        notification.save()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

@login_required
@require_http_methods(['POST'])
def mark_all_notifications_read(request):
    """Mark all notifications as read for the current user."""
    try:
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

class VerifyEmailView(View):
    def get(self, request, uidb64, token):
        try:
            # Decode the user ID
            from django.utils.http import urlsafe_base64_decode
            from django.utils.encoding import force_str
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
            
            # Check if already verified
            if user.email_verified:
                messages.info(request, 'Email already verified. You can now log in.')
                return redirect('login')
            
            # Check the token is valid
            from django.contrib.auth.tokens import default_token_generator
            if default_token_generator.check_token(user, token):
                # Mark email as verified
                user.email_verified = True
                user.save()
                messages.success(request, 'Your email has been verified successfully! You can now log in.')
                return redirect('login')
            else:
                messages.error(request, 'The verification link is invalid or has expired.')
                return redirect('login')
                
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            messages.error(request, 'The verification link is invalid or has expired.')
            return redirect('login')
