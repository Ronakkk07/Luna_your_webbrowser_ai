from django.urls import path

from .views import (
    AsyncVoiceCommandView,
    PageSummaryView,
    TextCommandView,
    VoiceCommandTaskStatusView,
    VoiceCommandView,
)

urlpatterns = [
    path("command/", TextCommandView.as_view(), name="text-command"),
    path("summarize-page/", PageSummaryView.as_view(), name="summarize-page"),
    path("voice/", VoiceCommandView.as_view(), name="voice-command"),
    path("voice/async/", AsyncVoiceCommandView.as_view(), name="voice-command-async"),
    path(
        "voice/tasks/<str:task_id>/",
        VoiceCommandTaskStatusView.as_view(),
        name="voice-command-task-status",
    ),
]
