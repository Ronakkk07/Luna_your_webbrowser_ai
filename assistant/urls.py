from django.urls import path
from .views import VoiceCommandView

urlpatterns = [
    path('voice/', VoiceCommandView.as_view(), name='voice-command'),
]