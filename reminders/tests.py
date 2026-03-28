from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Reminder


class DueReminderTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="testuser",
            password="StrongPassword123",
        )
        self.client.force_authenticate(user=self.user)

    def test_due_endpoint_returns_due_and_marks_notified(self):
        due = Reminder.objects.create(
            user=self.user,
            task="Pay rent",
            date_time=timezone.now() - timedelta(minutes=1),
        )

        response = self.client.get("/api/reminders/due/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], due.id)

        due.refresh_from_db()
        self.assertTrue(due.notified)

    def test_due_endpoint_does_not_return_future_reminders(self):
        Reminder.objects.create(
            user=self.user,
            task="Meeting tomorrow",
            date_time=timezone.now() + timedelta(hours=2),
        )

        response = self.client.get("/api/reminders/due/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    @patch("reminders.tasks.trigger_reminder.apply_async")
    @patch("reminders.tasks.transaction.on_commit", side_effect=lambda callback: callback())
    def test_create_endpoint_schedules_celery_for_future_reminder(
        self,
        mock_on_commit,
        mock_apply_async,
    ):
        future_time = (timezone.now() + timedelta(hours=1)).isoformat()

        response = self.client.post(
            "/api/reminders/",
            {
                "task": "Dentist appointment",
                "date_time": future_time,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(mock_on_commit.call_count, 1)
        self.assertEqual(mock_apply_async.call_count, 1)
