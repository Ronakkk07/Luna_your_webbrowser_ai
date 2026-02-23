from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .services.speech import transcribe_audio
from .services.llm import analyze_intent
from .services.router import route_intent


class VoiceCommandView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        audio_file = request.FILES.get("audio")

        if not audio_file:
            return Response(
                {"error": "No audio file provided"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 1️⃣ Speech-to-Text
        transcript = transcribe_audio(audio_file)

        # 2️⃣ LLM Intent Detection
        intent_data = analyze_intent(transcript)

        # 3️⃣ Route Intent
        result = route_intent(intent_data, request.user)

        return Response({
            "transcript": transcript,
            "intent": intent_data,
            "response": result
        })