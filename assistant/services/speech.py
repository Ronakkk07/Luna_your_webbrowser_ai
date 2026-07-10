import os
import tempfile

from django.conf import settings


class WhisperDisabled(Exception):
    """Raised when server-side transcription is turned off (ENABLE_WHISPER=False)."""


_model = None


def _get_model():
    """Lazily load Whisper on first use (it needs ~1GB RAM), and only if enabled.

    Loading lazily keeps the server booting fast/small on hosts where Whisper is
    disabled — the extension's mic button still does accurate STT client-side.
    """
    global _model
    if not getattr(settings, "ENABLE_WHISPER", True):
        raise WhisperDisabled()
    if _model is None:
        from faster_whisper import WhisperModel  # heavy import — defer it

        _model = WhisperModel(
            getattr(settings, "WHISPER_MODEL", "base.en"),
            device="cpu",
            compute_type="int8",
        )
    return _model


def transcribe_audio_path(audio_path):
    model = _get_model()
    segments, _ = model.transcribe(audio_path)
    text = " ".join([segment.text for segment in segments])
    return text.strip()


def transcribe_audio(audio_file):
    """
    Takes Django UploadedFile and returns transcript text.
    Works safely on Windows.
    """
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".wav")

    try:
        with os.fdopen(tmp_fd, "wb") as tmp:
            for chunk in audio_file.chunks():
                tmp.write(chunk)

        return transcribe_audio_path(tmp_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
