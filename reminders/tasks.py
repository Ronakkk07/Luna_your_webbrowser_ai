from celery import shared_task
from django.utils import timezone
from .models import Reminder

@shared_task
def trigger_reminder(reminder_id):
    try:
        reminder = Reminder.objects.get(id=reminder_id)
        if reminder.date_time <= timezone.now() and not reminder.notified:
            print(
                f"Reminder due for user {reminder.user.username}: "
                f"{reminder.task} ({reminder.date_time})"
            )
            return True

        return False
    except Reminder.DoesNotExist:
        print(f"Reminder {reminder_id} does not exist")
        return False
    except Exception as e:
        # catch everything else so the worker doesn’t crash
        print(f"Error in trigger_reminder: {e}")
        return False