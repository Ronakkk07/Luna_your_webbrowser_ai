from faster_whisper import WhisperModel
import tempfile

# Load once globally
model = WhisperModel("base", compute_type="int8")

def transcribe_audio(audio_file):
    with tempfile.NamedTemporaryFile(delete=True, suffix=".wav") as temp:
        for chunk in audio_file.chunks():
            temp.write(chunk)
        temp.flush()

        segments, _ = model.transcribe(temp.name)

        text = ""
        for segment in segments:
            text += segment.text + " "

    return text.strip()