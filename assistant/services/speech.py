from faster_whisper import WhisperModel
import tempfile
import os

# Load Whisper model once globally
model = WhisperModel("base", device="cpu" ,compute_type="int8")

def transcribe_audio(audio_file):
    """
    Takes Django UploadedFile and returns transcript text.
    Works safely on Windows.
    """
    # Create a temporary file safely for Windows
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".wav")
    
    try:
        # Write uploaded chunks to temp file and close immediately
        with os.fdopen(tmp_fd, "wb") as tmp:
            for chunk in audio_file.chunks():
                tmp.write(chunk)

        # Now the file is closed — safe for Whisper to read
        segments, _ = model.transcribe(tmp_path)

        # Combine all segments into one string
        text = " ".join([segment.text for segment in segments])

        return text.strip()

    finally:
        # Delete temp file
        if os.path.exists(tmp_path):
            os.remove(tmp_path)