import os

from celery import shared_task
from django.contrib.auth import get_user_model

from assistant.services.llm import analyze_intent
from assistant.services.router import route_intent
from assistant.services.speech import transcribe_audio_path


@shared_task
def process_voice_command_task(audio_path, user_id):
    user = get_user_model().objects.get(pk=user_id)

    try:
        transcript = transcribe_audio_path(audio_path)
        intent_data = analyze_intent(transcript)
        response_text = route_intent(intent_data, user)
        return {
            "transcript": transcript,
            "intent": intent_data,
            "response": response_text,
        }
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)
