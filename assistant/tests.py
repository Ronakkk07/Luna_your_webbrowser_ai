import os
import tempfile
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from .services.router import route_intent
from .tasks import process_voice_command_task


class AsyncAssistantTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="assistant-user",
            password="StrongPassword123",
        )
        self.client.force_authenticate(user=self.user)

    @patch("assistant.views.process_voice_command_task.delay")
    def test_async_voice_command_queues_task(self, mock_delay):
        mock_delay.return_value = Mock(id="task-123")

        response = self.client.post(
            "/api/assistant/voice/async/",
            {"audio_file": self._build_audio_file()},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data["task_id"], "task-123")
        mock_delay.assert_called_once()

    @patch("assistant.tasks.route_intent", return_value="Queued reminder created")
    @patch(
        "assistant.tasks.analyze_intent",
        return_value={
            "intent": "create_reminder",
            "task": "Pay rent",
            "datetime": "10 minutes",
            "items": [],
        },
    )
    @patch(
        "assistant.tasks.transcribe_audio_path",
        return_value="Remind me to pay rent in 10 minutes",
    )
    def test_process_voice_command_task_returns_result(
        self,
        mock_transcribe,
        mock_analyze,
        mock_route,
    ):
        audio_path = self._build_audio_path()

        result = process_voice_command_task.run(audio_path, self.user.id)

        self.assertEqual(result["response"], "Queued reminder created")
        self.assertEqual(
            result["transcript"],
            "Remind me to pay rent in 10 minutes",
        )
        self.assertFalse(os.path.exists(audio_path))
        mock_transcribe.assert_called_once_with(audio_path)
        mock_analyze.assert_called_once()
        mock_route.assert_called_once()

    @patch("assistant.tasks.route_intent", return_value="Dublin is in Ireland.")
    @patch(
        "assistant.tasks.analyze_intent",
        return_value={
            "intent": "get_city_info",
            "task": "What country is Dublin in?",
            "datetime": None,
            "items": [],
            "city": "Dublin",
            "city_field": "country",
        },
    )
    @patch(
        "assistant.tasks.transcribe_audio_path",
        return_value="What country is Dublin in?",
    )
    def test_process_voice_command_task_handles_city_info_requests(
        self,
        mock_transcribe,
        mock_analyze,
        mock_route,
    ):
        audio_path = self._build_audio_path()

        result = process_voice_command_task.run(audio_path, self.user.id)

        self.assertEqual(result["response"], "Dublin is in Ireland.")
        self.assertEqual(result["intent"]["intent"], "get_city_info")
        self.assertFalse(os.path.exists(audio_path))
        mock_transcribe.assert_called_once_with(audio_path)
        mock_analyze.assert_called_once_with("What country is Dublin in?")
        mock_route.assert_called_once()

    def _build_audio_file(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        return SimpleUploadedFile(
            "command.wav",
            b"fake audio bytes",
            content_type="audio/wav",
        )

    def _build_audio_path(self):
        handle = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        handle.write(b"fake audio bytes")
        handle.close()
        return handle.name


class AssistantRouterTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="router-user",
            password="StrongPassword123",
        )

    @patch("assistant.services.router.fetch_city_info")
    def test_route_intent_returns_specific_city_field(self, mock_fetch_city_info):
        mock_fetch_city_info.return_value = {
            "city": "Dublin",
            "country": "Ireland",
            "population": 5458600,
            "timezone": {"name": "Europe/Dublin", "offset_string": "+0000"},
            "languages": ["English", "Irish"],
            "currencies": [{"code": "EUR", "name": "euro", "symbol": "EUR"}],
        }

        response = route_intent(
            {
                "intent": "get_city_info",
                "task": "What is the population of Dublin?",
                "city": "Dublin",
                "city_field": "population",
            },
            self.user,
        )

        self.assertEqual(response, "The population of Dublin is 5,458,600.")
        mock_fetch_city_info.assert_called_once_with("Dublin")

    @patch("assistant.services.router.fetch_city_info")
    def test_route_intent_returns_city_summary(self, mock_fetch_city_info):
        mock_fetch_city_info.return_value = {
            "city": "Dublin",
            "country": "Ireland",
            "country_code": "IE",
            "population": 5458600,
            "formatted_address": "Dublin, Ireland",
            "latitude": 53.3493795,
            "longitude": -6.2605593,
            "timezone": {"name": "Europe/Dublin", "offset_string": "+0000"},
            "languages": ["English", "Irish"],
            "currencies": [{"code": "EUR", "name": "euro", "symbol": "EUR"}],
        }

        response = route_intent(
            {
                "intent": "get_city_info",
                "task": "Tell me about Dublin.",
                "city": "Dublin",
                "city_field": None,
            },
            self.user,
        )

        self.assertIn("Dublin is a city in Ireland", response)
        self.assertIn("country code IE", response)
        self.assertIn("5,458,600", response)
        self.assertIn("Dublin, Ireland", response)
        self.assertIn("Europe/Dublin", response)
        self.assertIn("English, Irish", response)
        self.assertIn("euro (EUR, symbol EUR)", response)
        self.assertIn("\n\n", response)

    def test_route_intent_handles_missing_city(self):
        response = route_intent(
            {
                "intent": "get_city_info",
                "task": "Tell me about that city.",
                "city": None,
                "city_field": None,
            },
            self.user,
        )

        self.assertEqual(response, "I couldn't tell which city you meant.")
