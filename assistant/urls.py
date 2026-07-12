from django.urls import path

from .views import (
    AsyncVoiceCommandView,
    FindHistoryView,
    PageAnswerView,
    PageSummaryView,
    TextCommandView,
    TranscribeView,
    UserSettingsView,
    VoiceCommandTaskStatusView,
    VoiceCommandView,
)

urlpatterns = [
    path("command/", TextCommandView.as_view(), name="text-command"),
    path("settings/", UserSettingsView.as_view(), name="user-settings"),
    path("find-history/", FindHistoryView.as_view(), name="find-history"),
    path("transcribe/", TranscribeView.as_view(), name="transcribe"),
    path("summarize-page/", PageSummaryView.as_view(), name="summarize-page"),
    path("answer-page/", PageAnswerView.as_view(), name="answer-page"),
    path("voice/", VoiceCommandView.as_view(), name="voice-command"),
    path("voice/async/", AsyncVoiceCommandView.as_view(), name="voice-command-async"),
    path(
        "voice/tasks/<str:task_id>/",
        VoiceCommandTaskStatusView.as_view(),
        name="voice-command-task-status",
    ),
]
