from pathlib import Path
from uuid import uuid4

from celery.result import AsyncResult
from django.conf import settings
from rest_framework import status
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .services.llm import analyze_intent, answer_about_page, summarize_page_text
from .services.router import route_intent
from .services.speech import WhisperDisabled, transcribe_audio
from .tasks import process_voice_command_task


def _run_command(text, user):
    """Shared pipeline: text -> intent -> action plan (with conversation memory)."""
    from .services import memory

    intent_data = analyze_intent(text, user_id=user.id)
    intent_data["_text"] = text  # preserve the raw utterance for Q&A
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
        return Response(_run_command(text, request.user))


class PageSummaryView(APIView):
    """Summarize page text extracted by the extension: JSON {text, title}."""

    parser_classes = [JSONParser]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        text = request.data.get("text") or ""
        title = request.data.get("title") or ""
        summary = summarize_page_text(text, title)
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
        return Response({"speak": answer_about_page(text, question, title)})


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
