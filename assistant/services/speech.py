import os
import tempfile

from faster_whisper import WhisperModel

# Load Whisper model once globally.
model = WhisperModel("base", device="cpu", compute_type="int8")


def transcribe_audio_path(audio_path):
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
