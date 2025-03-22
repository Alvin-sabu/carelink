from django import forms
from .models import HealthLog, Task, Medication, Communication, CareRequest, User, HealthDocument, HealthCheckSchedule
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm
from django.core.exceptions import ValidationError
from django.contrib.auth import authenticate

class UserRegistrationForm(UserCreationForm):
    USER_TYPES = (
        ('CAREGIVER', 'Caregiver'),
        ('FAMILY', 'Family Member'),
    )
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    email = forms.EmailField(required=True)
    phone_number = forms.CharField(max_length=15, required=False)
    user_type = forms.ChoiceField(choices=USER_TYPES, required=True)
    profile_picture = forms.ImageField(required=False)
    
    class Meta:
        model = User
        fields = [
            'first_name', 
            'last_name', 
            'email', 
            'phone_number',
            'username', 
            'password1', 
            'password2', 
            'user_type',
            'profile_picture'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['first_name'].widget.attrs.update({'class': 'form-control'})
        self.fields['last_name'].widget.attrs.update({'class': 'form-control'})
        self.fields['email'].widget.attrs.update({'class': 'form-control'})
        self.fields['phone_number'].widget.attrs.update({'class': 'form-control'})
        self.fields['username'].widget.attrs.update({'class': 'form-control'})
        self.fields['password1'].widget.attrs.update({'class': 'form-control'})
        self.fields['password2'].widget.attrs.update({'class': 'form-control'})
        self.fields['user_type'].widget.attrs.update({'class': 'form-control'})
        self.fields['profile_picture'].widget.attrs.update({'class': 'form-control'})

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.phone_number = self.cleaned_data['phone_number']
        user.user_type = self.cleaned_data['user_type']
        
        if commit:
            user.save()
            if self.cleaned_data.get('profile_picture'):
                user.profile_picture = self.cleaned_data['profile_picture']
                user.save()
        
        return user

class UserProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone_number', 'profile_picture']
        widgets = {
            'first_name': forms.TextInput(attrs={'placeholder': 'Enter your first name'}),
            'last_name': forms.TextInput(attrs={'placeholder': 'Enter your last name'}),
            'email': forms.EmailInput(attrs={'placeholder': 'Enter your email address'}),
            'phone_number': forms.TextInput(attrs={'placeholder': 'Enter your phone number'}),
            'profile_picture': forms.FileInput(attrs={'class': 'form-control'})
        }

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and User.objects.exclude(pk=self.instance.pk).filter(email=email).exists():
            raise forms.ValidationError('This email address is already in use.')
        return email

    def clean_phone_number(self):
        phone_number = self.cleaned_data.get('phone_number')
        if phone_number:
            # Remove any non-digit characters
            phone_number = ''.join(filter(str.isdigit, phone_number))
            # Validate length
            if len(phone_number) < 10:
                raise forms.ValidationError('Phone number must be at least 10 digits.')
        return phone_number

class HealthLogForm(forms.ModelForm):
    temperature = forms.DecimalField(
        min_value=35.0,
        max_value=42.0,
        decimal_places=1,
        help_text="Temperature should be between 35.0°C and 42.0°C"
    )
    blood_pressure = forms.CharField(
        max_length=10,
        help_text="Format: systolic/diastolic (e.g., 120/80)"
    )
    pulse_rate = forms.IntegerField(
        min_value=40,
        max_value=200,
        help_text="Pulse rate should be between 40-200 BPM"
    )
    
    class Meta:
        model = HealthLog
        fields = ['temperature', 'blood_pressure', 'pulse_rate', 'notes']
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 4}),
        }

    def clean_blood_pressure(self):
        bp = self.cleaned_data.get('blood_pressure')
        if bp:
            try:
                systolic, diastolic = map(int, bp.split('/'))
                if not (70 <= systolic <= 200):
                    raise forms.ValidationError("Systolic pressure should be between 70-200 mmHg")
                if not (40 <= diastolic <= 130):
                    raise forms.ValidationError("Diastolic pressure should be between 40-130 mmHg")
                if systolic <= diastolic:
                    raise forms.ValidationError("Systolic pressure must be greater than diastolic pressure")
            except ValueError:
                raise forms.ValidationError("Blood pressure must be in format: systolic/diastolic (e.g., 120/80)")
        return bp

class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ['title', 'description', 'category', 'priority', 'due_date', 'patient']
        widgets = {
            'due_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'description': forms.Textarea(attrs={'rows': 4}),
        }

class MedicationForm(forms.ModelForm):
    class Meta:
        model = Medication
        fields = [
            'name',
            'dosage',
            'frequency',
            'start_date',
            'end_date',
            'prescribing_doctor',
            'pharmacy_name',
            'pharmacy_phone',
            'refills_remaining',
            'next_refill_date',
            'notes',
            'instructions'
        ]
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'next_refill_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'instructions': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'})
        }

class CommunicationForm(forms.ModelForm):
    patient_id = forms.IntegerField(widget=forms.HiddenInput())  # Add patient_id field

    class Meta:
        model = Communication
        fields = ['message', 'patient_id']  # Include patient_id in the fields
        widgets = {
            'message': forms.Textarea(attrs={'rows': 4}),
        }

class CareRequestForm(forms.ModelForm):
    REQUEST_TYPE_CHOICES = [
        ('HOME_CARE', 'Home Care'),
        ('MEDICAL_ASSISTANCE', 'Medical Assistance'),
        ('RESPITE_CARE', 'Respite Care'),
        ('SPECIALIZED_CARE', 'Specialized Care')
    ]
    
    request_type = forms.ChoiceField(
        choices=REQUEST_TYPE_CHOICES, 
        widget=forms.Select(attrs={'class': 'form-control'}),
        required=True,
        label='Request Type'
    )

    patient_name = forms.CharField(
        max_length=100, 
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        required=True,
        label='Patient First Name'
    )

    patient_last_name = forms.CharField(
        max_length=100, 
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        required=False,
        label='Patient Last Name'
    )

    patient_date_of_birth = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        required=True,
        label='Date of Birth'
    )

    patient_condition = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        required=True,
        label='Medical Condition'
    )

    emergency_contact = forms.CharField(
        max_length=15,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        required=False,
        label='Emergency Contact Number'
    )

    patient_address = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        required=False,
        label='Patient Address'
    )

    class Meta:
        model = CareRequest
        fields = [
            'request_type', 
            'patient_name', 
            'patient_last_name', 
            'patient_date_of_birth', 
            'patient_condition', 
            'emergency_contact', 
            'patient_address'
        ]

    def save(self, commit=True):
        care_request = super().save(commit=False)
        care_request.patient_name = f"{self.cleaned_data['patient_name']} {self.cleaned_data.get('patient_last_name', '')}"
        
        if commit:
            care_request.save()
        return care_request

class HealthDocumentForm(forms.ModelForm):
    class Meta:
        model = HealthDocument
        fields = ['title', 'document']


# forms.py

from django import forms
from .models import Medication, MedicationSchedule, MedicationLog

class MedicationScheduleForm(forms.ModelForm):
    class Meta:
        model = MedicationSchedule
        fields = ['scheduled_time', 'dosage_amount']
        widgets = {
            'scheduled_time': forms.TimeInput(attrs={'type': 'time'}),
        }

class MedicationLogForm(forms.ModelForm):
    class Meta:
        model = MedicationLog
        fields = ['status', 'notes']

MedicationScheduleFormSet = forms.inlineformset_factory(
    Medication, 
    MedicationSchedule,
    form=MedicationScheduleForm,
    extra=1,
    can_delete=True
)

class HealthCheckScheduleForm(forms.ModelForm):
    class Meta:
        model = HealthCheckSchedule
        fields = ['patient', 'caregiver', 'next_check', 'is_active']
        widgets = {
            'next_check': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

class CustomAuthenticationForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        'email_not_verified': 'Please verify your email address before logging in.',
    }

    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if username is not None and password:
            try:
                self.user_cache = authenticate(self.request, username=username, password=password)
            except ValidationError:
                raise ValidationError(
                    self.error_messages['email_not_verified'],
                    code='email_not_verified'
                )
            
            if self.user_cache is None:
                raise ValidationError(
                    self.error_messages['invalid_login'],
                    code='invalid_login',
                    params={'username': self.username_field.verbose_name},
                )
            else:
                self.confirm_login_allowed(self.user_cache)

        return self.cleaned_data