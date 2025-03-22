# carelink/apps.py
from django.apps import AppConfig

class CarelinkConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'carelink'

    def ready(self):
        import carelink.signals
