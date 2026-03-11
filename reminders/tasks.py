from celery import shared_task
from .models import Reminder

@shared_task
def trigger_reminder(reminder_id):
    try:
        reminder = Reminder.objects.get(id=reminder_id)
        # Optional: log reminder
        print(f"Reminder triggered for user {reminder.user.username}: {reminder.task}")

        # You can send email or notification here
        # Or mark reminder as sent
        reminder.sent = True
        reminder.save()
    except Reminder.DoesNotExist:
        print(f"Reminder {reminder_id} does not exist")
    except Exception as e:
        # catch everything else so the worker doesn’t crash
        print(f"Error in trigger_reminder: {e}")