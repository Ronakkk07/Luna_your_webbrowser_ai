import os
import tempfile
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from .models import UserSettings
from .services import crypto, memory, providers, retrieval
from .services.agent import run_agent
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

    @patch(
        "assistant.tasks.route_intent",
        return_value={"speak": "Reminder set.", "actions": []},
    )
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
    def test_process_voice_command_task_returns_plan(
        self, mock_transcribe, mock_analyze, mock_route
    ):
        audio_path = self._build_audio_path()

        result = process_voice_command_task.run(audio_path, self.user.id)

        # Current contract: {transcript, intent, speak, actions}.
        self.assertEqual(result["speak"], "Reminder set.")
        self.assertEqual(result["transcript"], "Remind me to pay rent in 10 minutes")
        self.assertEqual(result["actions"], [])
        self.assertFalse(os.path.exists(audio_path))  # temp file cleaned up
        mock_transcribe.assert_called_once_with(audio_path)
        mock_analyze.assert_called_once()
        mock_route.assert_called_once()

    def _build_audio_file(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        return SimpleUploadedFile(
            "command.wav", b"fake audio bytes", content_type="audio/wav"
        )

    def _build_audio_path(self):
        handle = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        handle.write(b"fake audio bytes")
        handle.close()
        return handle.name


class RouterContractTests(TestCase):
    """route_intent always returns the {speak, actions} action-plan contract."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="router-user", password="StrongPassword123"
        )

    def _plan(self, data):
        return route_intent(data, self.user)

    def test_get_time_speaks_without_action(self):
        plan = self._plan({"intent": "get_time"})
        self.assertIn("speak", plan)
        self.assertEqual(plan["actions"], [])
        self.assertTrue(plan["speak"])

    def test_open_tab_emits_action_with_normalized_url(self):
        plan = self._plan({"intent": "open_tab", "url": "example.com"})
        self.assertEqual(plan["actions"][0]["type"], "open_tab")
        self.assertTrue(plan["actions"][0]["url"].startswith("https://"))

    def test_highlight_emits_highlight_action(self):
        plan = self._plan({"intent": "highlight", "query": "the price"})
        self.assertEqual(plan["actions"][0]["type"], "highlight")
        self.assertEqual(plan["actions"][0]["query"], "the price")

    def test_find_history_emits_find_history_action(self):
        plan = self._plan({"intent": "find_history", "query": "gpus"})
        self.assertEqual(plan["actions"][0]["type"], "find_history")
        self.assertEqual(plan["actions"][0]["query"], "gpus")

    def test_unknown_intent_is_handled_gracefully(self):
        plan = self._plan({"intent": "nonsense-intent"})
        self.assertIn("speak", plan)
        self.assertIsInstance(plan["actions"], list)


class ProviderSelectionTests(TestCase):
    """Cost model: keyless -> free model; BYO key -> their model; casual -> always free."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="provider-user", password="StrongPassword123"
        )

    def test_keyless_user_gets_free_provider(self):
        provider, is_free = providers.pick(self.user.id, "standard")
        self.assertTrue(is_free)
        self.assertIsInstance(provider, providers.FreeProvider)

    def test_byo_key_used_for_standard_but_free_for_casual(self):
        s = UserSettings.objects.create(user=self.user, llm_provider="gemini")
        s.set_api_key("secret-key")
        s.save()

        provider, is_free = providers.pick(self.user.id, "standard")
        self.assertFalse(is_free)
        self.assertIsInstance(provider, providers.GeminiProvider)

        provider, is_free = providers.pick(self.user.id, "casual")
        self.assertTrue(is_free)  # casual conserves the user's key


class CryptoAndMemoryTests(TestCase):
    def test_api_key_encrypts_and_round_trips(self):
        token = crypto.encrypt("my-api-key")
        self.assertNotEqual(token, "my-api-key")
        self.assertEqual(crypto.decrypt(token), "my-api-key")
        self.assertEqual(crypto.decrypt(""), "")

    def test_conversation_memory_round_trip(self):
        uid = 424242
        memory.clear(uid)
        memory.add_turn(uid, "user", "who won the world cup")
        memory.add_turn(uid, "assistant", "Argentina in 2022.")
        self.assertEqual(len(memory.get_turns(uid)), 2)
        self.assertIn("Argentina", memory.history_text(uid))
        memory.clear(uid)
        self.assertEqual(memory.get_turns(uid), [])


class AgentLoopTests(TestCase):
    """The agentic loop chains server tools then finalizes {speak, actions};
    it degrades to None (caller falls back) on malformed model output."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="agent-user", password="StrongPassword123"
        )

    @patch("assistant.services.agent.providers.complete")
    def test_calls_tool_then_finalizes(self, mock_complete):
        mock_complete.side_effect = [
            '{"action":"call_tool","tool":"get_time","args":{}}',
            '{"action":"final","speak":"Here you go.","browser_actions":[{"type":"open_tab","url":"https://example.com"}]}',
        ]
        plan = run_agent("what time is it, then open example", self.user)
        self.assertEqual(plan["speak"], "Here you go.")
        self.assertEqual(plan["actions"][0]["type"], "open_tab")
        self.assertEqual(mock_complete.call_count, 2)  # tool call, then final

    @patch("assistant.services.agent.providers.complete", return_value="this is not json")
    def test_malformed_output_falls_back(self, mock_complete):
        self.assertIsNone(run_agent("hello there", self.user))

    @patch(
        "assistant.services.agent.providers.complete",
        return_value='{"action":"final","speak":"ok","browser_actions":[{"type":"evil"},{"type":"highlight","query":"x"}]}',
    )
    def test_finalize_sanitizes_unknown_actions(self, mock_complete):
        plan = run_agent("highlight x", self.user)
        self.assertEqual(len(plan["actions"]), 1)
        self.assertEqual(plan["actions"][0]["type"], "highlight")


class RetrievalTests(TestCase):
    def test_top_passages_prefers_relevant_chunk(self):
        text = (
            "Cats and dogs are common pets.\n\n"
            + ("filler about weather. " * 60)
            + "\n\nThe refund policy allows returns within 30 days for a full refund.\n\n"
            + ("filler about history. " * 60)
        )
        out = retrieval.top_passages(text, "what is the refund policy", k=2, max_chars=4000)
        self.assertIn("refund", out.lower())
        self.assertLess(len(out), len(text))  # retrieved a subset, not the whole page
