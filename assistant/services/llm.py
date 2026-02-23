import google.generativeai as genai
from django.conf import settings
import json

genai.configure(api_key=settings.GEMINI_API_KEY)

model = genai.GenerativeModel("gemini-1.5-flash")


def analyze_intent(text):
    prompt = f"""
You are an intelligent voice assistant.

Extract structured intent from the command below.

Command:
"{text}"

Return ONLY valid JSON in this exact format:

{{
  "intent": "create_reminder | add_shopping | summarize | unknown",
  "task": "string or null",
  "datetime": "string or null",
  "items": ["item1", "item2"]
}}

No explanations. Only JSON.
"""

    response = model.generate_content(prompt)

    try:
        cleaned = response.text.strip()
        return json.loads(cleaned)
    except Exception:
        return {
            "intent": "unknown",
            "task": text,
            "datetime": None,
            "items": []
        }