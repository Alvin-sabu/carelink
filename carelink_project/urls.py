from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from django.urls import re_path
from carelink.forms import CustomAuthenticationForm
from carelink.admin import admin_site

urlpatterns = [
    path('admin/', admin_site.urls),
    path('carelink/', include('carelink.urls', namespace='carelink')),
    path('carelink/accounts/login/', auth_views.LoginView.as_view(
        template_name='registration/login.html',
        authentication_form=CustomAuthenticationForm,
        next_page='carelink:home'
    ), name='login'),
    re_path(r'^media/(?P<path>.*)$', serve, {
        'document_root': settings.MEDIA_ROOT,
        'show_indexes': True
    }),
    path('', include('carelink.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)