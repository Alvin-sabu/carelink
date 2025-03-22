from django.db.models.signals import post_save
from django.dispatch import receiver
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import Task, HealthLog, Communication, Notification, Medication

@receiver(post_save, sender=Task)
def task_notification(sender, instance, created, **kwargs):
    if created:
        create_notification(
            instance.caregiver,
            'TASK',
            'New Task Assigned',
            f'You have been assigned a new task: {instance.title}'
        )

@receiver(post_save, sender=HealthLog)
def health_log_notification(sender, instance, created, **kwargs):
    if created:
        for family_member in instance.patient.family_members.all():
            create_notification(
                family_member,
                'HEALTH',
                'New Health Log',
                f'New health log added for {instance.patient.first_name}'
            )

@receiver(post_save, sender=Communication)
def message_notification(sender, instance, created, **kwargs):
    if created:
        create_notification(
            instance.receiver,
            'MESSAGE',
            'New Message',
            f'You have a new message from {instance.sender.get_full_name()}'
        )

@receiver(post_save, sender=Medication)
def medication_notification(sender, instance, created, **kwargs):
    if created:
        create_notification(
            instance.patient.assigned_caregiver,
            'SYSTEM',
            'New Medication Added',
            f'New medication ({instance.name}) added for {instance.patient.first_name}'
        )

def create_notification(user, notification_type, title, message):
    # Create notification in database
    notification = Notification.objects.create(
        user=user,
        type=notification_type,
        title=title,
        message=message
    )

    # Send real-time notification through WebSocket
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f'user_{user.id}_notifications',
        {
            'type': 'notification_message',
            'message': {
                'id': notification.id,
                'type': notification_type,
                'title': title,
                'message': message,
                'created_at': notification.created_at.isoformat()
            }
        }
    )
