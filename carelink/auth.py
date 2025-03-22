from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

class EmailVerificationBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        try:
            user = UserModel.objects.get(username=username)
            if user.check_password(password):
                # Check if email is verified, user is superuser, or user is an existing user
                if user.is_superuser or (user.date_joined and (timezone.now() - user.date_joined).days > 1) or user.email_verified:
                    return user
                else:
                    raise ValidationError(
                        'Please verify your email address before logging in.',
                        code='email_not_verified'
                    )
            return None
        except UserModel.DoesNotExist:
            return None

    def get_user(self, user_id):
        UserModel = get_user_model()
        try:
            return UserModel.objects.get(pk=user_id)
        except UserModel.DoesNotExist:
            return None 