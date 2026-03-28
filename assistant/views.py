from pathlib import Path
from uuid import uuid4

from celery.result import AsyncResult
from django.conf import settings
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .services.llm import analyze_intent
from .services.router import route_intent
from .services.speech import transcribe_audio
from .tasks import process_voice_command_task


class VoiceCommandView(APIView):
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
        intent_data = analyze_intent(transcript)
        result = route_intent(intent_data, request.user)

        return Response(
            {
                "transcript": transcript,
                "intent": intent_data,
                "response": result,
            }
        )


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
