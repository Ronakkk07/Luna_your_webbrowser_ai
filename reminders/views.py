from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.decorators import action
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from .models import Reminder
from .serializers import ReminderSerializer

class ReminderViewSet(viewsets.ModelViewSet):
    serializer_class = ReminderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Reminder.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    # ✅ Custom action for due reminders
    @action(detail=False, methods=['get'], url_path='due')
    def due_reminders(self, request):
        now = timezone.now()
        reminders = (
            self.get_queryset()
            .filter(date_time__lte=now, notified=False)
            .order_by("date_time")
        )

        data = [
            {
                "id": r.id,
                "task": r.task,
                "date_time": r.date_time.strftime("%Y-%m-%d %H:%M"),
            }
            for r in reminders
        ]
        reminders.update(notified=True)

        return Response(data)
