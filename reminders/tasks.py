from celery import shared_task
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import Reminder


def build_reminder_datetime(dt_str):
    if not dt_str:
        return timezone.now()

    try:
        dt_str_lower = dt_str.lower().strip()
        if "minute" in dt_str_lower:
            num = int(dt_str_lower.split("minute")[0].strip())
            return timezone.now() + timezone.timedelta(minutes=num)
        if "hour" in dt_str_lower:
            num = int(dt_str_lower.split("hour")[0].strip())
            return timezone.now() + timezone.timedelta(hours=num)
        if "day" in dt_str_lower:
            num = int(dt_str_lower.split("day")[0].strip())
            return timezone.now() + timezone.timedelta(days=num)

        parsed = parse_datetime(dt_str.replace(".", ":"))
        if parsed is None:
            return timezone.now()
        if timezone.is_naive(parsed):
            return timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed
    except Exception:
        return timezone.now()


def schedule_reminder_trigger(reminder):
    delay = max((reminder.date_time - timezone.now()).total_seconds(), 0)

    def enqueue():
        if delay > 0:
            trigger_reminder.apply_async(args=[reminder.id], countdown=delay)
        else:
            trigger_reminder.delay(reminder.id)

    transaction.on_commit(enqueue)


def create_reminder_for_user(user, task_name, dt):
    reminder = Reminder.objects.create(user=user, task=task_name, date_time=dt)
    schedule_reminder_trigger(reminder)
    return reminder


@shared_task
def trigger_reminder(reminder_id):
    try:
        reminder = Reminder.objects.get(id=reminder_id)
        if reminder.date_time <= timezone.now() and not reminder.notified:
            reminder.notified = True
            reminder.save(update_fields=["notified"])
            print(
                f"Reminder due for user {reminder.user.username}: "
                f"{reminder.task} ({reminder.date_time})"
            )
            return True

        return False
    except Reminder.DoesNotExist:
        print(f"Reminder {reminder_id} does not exist")
        return False
    except Exception as exc:
        print(f"Error in trigger_reminder: {exc}")
        return False
