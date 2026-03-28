from django.urls import path

from .views import AsyncVoiceCommandView, VoiceCommandTaskStatusView, VoiceCommandView

urlpatterns = [
    path("voice/", VoiceCommandView.as_view(), name="voice-command"),
    path("voice/async/", AsyncVoiceCommandView.as_view(), name="voice-command-async"),
    path(
        "voice/tasks/<str:task_id>/",
        VoiceCommandTaskStatusView.as_view(),
        name="voice-command-task-status",
    ),
]
