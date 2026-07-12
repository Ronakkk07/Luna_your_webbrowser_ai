from pathlib import Path
from uuid import uuid4

from celery.result import AsyncResult
from django.conf import settings
from rest_framework import status
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .services.llm import (
    analyze_intent,
    answer_about_page,
    rank_history,
    summarize_page_text,
)
from .services.router import route_intent
from .services.speech import WhisperDisabled, transcribe_audio
from .tasks import process_voice_command_task


# Reasoning-heavy intents benefit from the multi-step agent; obvious deterministic
# commands (open a tab, time, play youtube, tabs, reminders) keep the fast, no-LLM
# path to conserve cost.
_AGENT_INTENTS = {"answer_question", "web_research", "unknown", "chitchat", "ask_page", "open_and_answer"}


def _run_command(text, user, tz=None):
    """Shared pipeline: text -> intent -> action plan (with conversation memory)."""
    from django.conf import settings

    from .services import memory

    intent_data = analyze_intent(text, user_id=user.id)
    intent_data["_text"] = text  # preserve the raw utterance for Q&A
    intent_data["_tz"] = tz  # client IANA timezone, for time/reminder formatting

    plan = None
    if getattr(settings, "ENABLE_AGENT", False) and intent_data.get("intent") in _AGENT_INTENTS:
        from .services.agent import run_agent

        history = memory.history_text(user.id)
        plan = run_agent(text, user, history=history)  # None -> fall back below

    if plan is None:
        plan = route_intent(intent_data, user)

    # Record the exchange so follow-ups have context next time.
    memory.add_turn(user.id, "user", text)
    memory.add_turn(user.id, "assistant", plan.get("speak", ""))

    return {
        "transcript": text,
        "intent": intent_data,
        "speak": plan.get("speak", ""),
        "actions": plan.get("actions", []),
    }


class TextCommandView(APIView):
    """Primary endpoint for the extension: JSON {text} -> {speak, actions}.

    The extension transcribes speech locally with the Web Speech API and sends
    the text here, so no audio upload is needed.
    """

    parser_classes = [JSONParser]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        text = (request.data.get("text") or "").strip()
        if not text:
            return Response(
                {"error": "No text provided"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        tz = request.data.get("tz") or None
        return Response(_run_command(text, request.user, tz=tz))


class PageSummaryView(APIView):
    """Summarize page text extracted by the extension: JSON {text, title}."""

    parser_classes = [JSONParser]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        text = request.data.get("text") or ""
        title = request.data.get("title") or ""
        summary = summarize_page_text(text, title, user_id=request.user.id)
        return Response({"speak": summary})


class TranscribeView(APIView):
    """Whisper-only: audio in → {transcript}. Used by the always-listen path
    (Vosk detects the wake word, then the command audio is transcribed here)."""

    parser_classes = [MultiPartParser]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        audio_file = request.FILES.get("audio_file")
        if not audio_file:
            return Response(
                {"error": "No audio file provided"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            return Response({"transcript": transcribe_audio(audio_file)})
        except WhisperDisabled:
            return Response(
                {"error": "Server transcription is disabled. Use the mic button."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


class PageAnswerView(APIView):
    """Answer a question about a page: JSON {text, question, title}."""

    parser_classes = [JSONParser]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        text = request.data.get("text") or ""
        question = request.data.get("question") or ""
        title = request.data.get("title") or ""
        return Response(
            {"speak": answer_about_page(text, question, title, user_id=request.user.id)}
        )


class VoiceCommandView(APIView):
    """Audio-upload fallback: transcribes with Whisper server-side."""

    parser_classes = [MultiPartParser]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        audio_file = request.FILES.get("audio_file")

        if not audio_file:
            return Response(
                {"error": "No audio file provided"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        transcript = transcribe_audio(audio_file)
        return Response(_run_command(transcript, request.user))


class AsyncVoiceCommandView(APIView):
    parser_classes = [MultiPartParser]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        audio_file = request.FILES.get("audio_file")

        if not audio_file:
            return Response(
                {"error": "No audio file provided"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        audio_path = self._store_upload(audio_file)
        task = process_voice_command_task.delay(str(audio_path), request.user.id)

        return Response(
            {
                "task_id": task.id,
                "state": "PENDING",
            },
            status=status.HTTP_202_ACCEPTED,
        )

    def _store_upload(self, audio_file):
        upload_dir = Path(settings.MEDIA_ROOT) / "voice_commands"
        upload_dir.mkdir(parents=True, exist_ok=True)

        audio_path = upload_dir / f"{uuid4().hex}_{audio_file.name}"
        with audio_path.open("wb") as destination:
            for chunk in audio_file.chunks():
                destination.write(chunk)

        return audio_path


class FindHistoryView(APIView):
    """Semantic browsing-history search. The extension gathers candidates from
    chrome.history (client-side, private) and posts {query, items:[{title,url}]};
    the server ranks them by meaning and returns {speak, matches:[{title,url}]}.
    """

    parser_classes = [JSONParser]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        query = (request.data.get("query") or "").strip()
        items = request.data.get("items") or []
        if not isinstance(items, list):
            items = []
        return Response(rank_history(query, items, user_id=request.user.id))


class UserSettingsView(APIView):
    """GET current assistant settings; POST to save the display name and an
    optional bring-your-own API key (stored encrypted). Send an empty api_key to
    clear it and fall back to the free model.
    """

    parser_classes = [JSONParser]
    permission_classes = [IsAuthenticated]

    VALID_PROVIDERS = {"gemini", "groq", "openai"}

    def _settings(self, user):
        from .models import UserSettings

        obj, _ = UserSettings.objects.get_or_create(user=user)
        return obj

    def get(self, request):
        s = self._settings(request.user)
        return Response(
            {
                "display_name": s.display_name,
                "llm_provider": s.llm_provider,
                "has_key": s.has_key,  # never return the key itself
            }
        )

    def post(self, request):
        s = self._settings(request.user)

        if "display_name" in request.data:
            s.display_name = (request.data.get("display_name") or "").strip()[:80]

        if "llm_provider" in request.data:
            provider = (request.data.get("llm_provider") or "").strip().lower()
            if provider and provider not in self.VALID_PROVIDERS:
                return Response(
                    {"error": f"Unknown provider '{provider}'."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            s.llm_provider = provider

        # api_key present (even empty) means set/clear it.
        if "api_key" in request.data:
            raw = (request.data.get("api_key") or "").strip()
            if raw and not s.llm_provider:
                s.llm_provider = "gemini"  # sensible default
            try:
                s.set_api_key(raw)
            except RuntimeError as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        s.save()
        return Response(
            {
                "display_name": s.display_name,
                "llm_provider": s.llm_provider,
                "has_key": s.has_key,
            }
        )


class VoiceCommandTaskStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, task_id):
        result = AsyncResult(task_id)
        payload = {
            "task_id": task_id,
            "state": result.state,
        }

        if result.successful():
            payload["result"] = result.result
        elif result.failed():
            payload["error"] = str(result.result)

        return Response(payload)
