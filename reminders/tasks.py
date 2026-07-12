import re

from celery import shared_task
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import Reminder

try:  # zoneinfo is stdlib on py3.9+
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

_UNIT_DELTAS = {
    "second": lambda n: timezone.timedelta(seconds=n),
    "minute": lambda n: timezone.timedelta(minutes=n),
    "hour": lambda n: timezone.timedelta(hours=n),
    "day": lambda n: timezone.timedelta(days=n),
    "week": lambda n: timezone.timedelta(weeks=n),
}


def build_reminder_datetime(dt_str, tz_name=None):
    """Turn a phrase like 'in 5 minutes', 'after 2 hours', or 'at 8:30 pm' into an
    absolute aware datetime. Relative phrases are timezone-independent; 'at <time>'
    is interpreted in the user's zone (``tz_name``) if provided.
    """
    if not dt_str:
        return timezone.now()

    try:
        s = str(dt_str).lower().strip()

        # Relative: "in/after N <unit>", "N <unit>", "N <unit> from now".
        m = re.search(r"(\d+)\s*(second|minute|hour|day|week)s?", s)
        if m:
            n = int(m.group(1))
            return timezone.now() + _UNIT_DELTAS[m.group(2)](n)

        # Absolute clock time today: "at 8", "at 8:30 pm", "at 20:00".
        tm = re.search(r"at\s+(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?", s)
        if tm:
            hour = int(tm.group(1))
            minute = int(tm.group(2) or 0)
            ap = (tm.group(3) or "").replace(".", "")
            if ap == "pm" and hour < 12:
                hour += 12
            if ap == "am" and hour == 12:
                hour = 0
            tz = ZoneInfo(tz_name) if (ZoneInfo and tz_name) else None
            now = timezone.localtime(timezone.now(), tz)
            target = now.replace(hour=min(hour, 23), minute=min(minute, 59), second=0, microsecond=0)
            if target <= now:  # that time already passed today -> tomorrow
                target += timezone.timedelta(days=1)
            return target

        parsed = parse_datetime(s.replace(".", ":"))
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
        # Best-effort: delivery is via the extension polling /api/reminders/due/,
        # so a missing Celery broker (e.g. local runserver with no worker) must not
        # break reminder creation.
        try:
            if delay > 0:
                trigger_reminder.apply_async(args=[reminder.id], countdown=delay)
            else:
                trigger_reminder.delay(reminder.id)
        except Exception as exc:  # broker down / not configured
            print(f"schedule_reminder_trigger: could not enqueue ({exc}); "
                  f"reminder will still be delivered by the /due/ poll.")

    transaction.on_commit(enqueue)


def create_reminder_for_user(user, task_name, dt):
    reminder = Reminder.objects.create(user=user, task=task_name, date_time=dt)
    schedule_reminder_trigger(reminder)
    return reminder


@shared_task
def trigger_reminder(reminder_id):
    """Fires at a reminder's due time (when a Celery worker is running).

    Delivery to the user happens through the extension polling
    ``/api/reminders/due/`` (which marks reminders notified as it returns them), so
    this task must NOT mark ``notified`` itself — otherwise it would consume the
    reminder before the poll can speak it. It's left as a hook for future
    server-push delivery (web push / websockets).
    """
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
    except Exception as exc:
        print(f"Error in trigger_reminder: {exc}")
        return False
