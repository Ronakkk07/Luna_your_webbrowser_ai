from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Reminder
from .serializers import ReminderSerializer
from .tasks import schedule_reminder_trigger


class ReminderViewSet(viewsets.ModelViewSet):
    serializer_class = ReminderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Reminder.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        reminder = serializer.save(user=self.request.user)
        schedule_reminder_trigger(reminder)

    @action(detail=False, methods=["get"], url_path="due")
    def due_reminders(self, request):
        now = timezone.now()
        reminders = (
            self.get_queryset()
            .filter(date_time__lte=now, notified=False)
            .order_by("date_time")
        )

        data = [
            {
                "id": reminder.id,
                "task": reminder.task,
                "date_time": reminder.date_time.strftime("%Y-%m-%d %H:%M"),
            }
            for reminder in reminders
        ]
        reminders.update(notified=True)

        return Response(data)
