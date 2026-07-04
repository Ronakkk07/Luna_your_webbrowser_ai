import google.generativeai as genai
from django.conf import settings
import json
import os
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

model = genai.GenerativeModel("models/gemini-2.5-flash")


def _fallback_intent(text):
    """When Gemini is unavailable, fall back to local keyword detection so the
    core browser commands keep working offline / under rate limits."""
    from assistant.services.intent import detect_intent

    return detect_intent(text)


def analyze_intent(text):
    prompt = f"""
You are Luna, an intelligent browser voice assistant (like Alexa, but living in the
browser). Extract a structured intent from the user's spoken command below.

Command:
"{text}"

Return ONLY valid JSON in this exact shape:

{{
  "intent": "create_reminder | add_shopping | summarize | list_reminders | list_shopping | open_tab | search_web | play_youtube | switch_tab | close_tab | list_tabs | summarize_page | get_time | get_news | unknown",
  "task": "string or null",
  "datetime": "string or null",
  "items": ["item1", "item2"],
  "query": "string or null",
  "url": "string or null",
  "tab_hint": "string or null"
}}

Guidance:
- "open_tab": user wants to open/go to a website. Put a full https URL in "url" when a
  known site is named (e.g. youtube -> https://www.youtube.com). If they describe a page
  but not a site, leave "url" null and put what they want in "query".
- "play_youtube": user wants to WATCH or PLAY something on YouTube (e.g. "open youtube
  and play lofi beats", "play the latest MKBHD video", "watch <song> on youtube"). Put
  the full thing to search/play (channel, title, keywords) in "query".
- "search_web": user wants to search the web / look something up. Put the search terms in "query".
- "switch_tab": user wants to move to an already-open tab. Put a describing word (e.g.
  "gmail", "the youtube tab") in "tab_hint".
- "close_tab": user wants to close a tab. Put its description in "tab_hint", or null for the current tab.
- "list_tabs": user asks what tabs are open.
- "summarize_page": user wants the current page summarized or read.
- "get_time": user asks for the current time or date.
- "get_news": user asks for news/headlines. Put a topic in "query" if they name one, else null.
- "create_reminder": put the reminder text in "task" and any time phrase in "datetime".
- "add_shopping": put items in "items".
- Anything conversational or unclear: "unknown".

No explanations. Only JSON.
"""

    try:
        response = model.generate_content(prompt)
        raw = response.text.strip()
    except Exception as e:  # network / API failure
        print("Gemini analyze_intent error:", e)
        return _fallback_intent(text)

    # Remove markdown wrapping if present
    cleaned = raw.replace("```json", "").replace("```", "").strip()

    try:
        data = json.loads(cleaned)
    except Exception:
        print("Gemini raw output:", raw)  # Debug
        return _fallback_intent(text)

    # Normalise so downstream code can rely on the keys existing.
    fallback = _fallback_intent(text)
    for key, default in fallback.items():
        data.setdefault(key, default)
    return data

def small_chatbot_response(transcript: str) -> str:
    """
    Handle casual conversation for unknown intents.
    Returns a friendly response.
    """
    prompt = f"""
You are a friendly AI assistant.
Respond naturally and helpfully to the following user message:

User: "{transcript}"

If the message is casual (hello, thank you, how are you, etc.) respond naturally.
If the message asks a task you cannot do, reply politely that you can't.
Return only the assistant's text, no JSON.
"""

    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print("Error generating casual response:", e)
        return "Sorry, I didn't understand that command."


def summarize_page_text(text: str, title: str = "") -> str:
    """Summarize the visible text of a web page into a short spoken summary."""
    snippet = (text or "").strip()
    if not snippet:
        return "There's no readable text on this page to summarize."

    # Keep the prompt within a sane size; page text can be huge.
    snippet = snippet[:12000]
    heading = f'Page title: "{title}"\n' if title else ""
    prompt = f"""
You are Luna, a browser voice assistant. Summarize the web page content below in
3 to 5 short spoken sentences a person can listen to. Be concise and factual.

{heading}Page content:
\"\"\"
{snippet}
\"\"\"

Return only the summary text, no preamble.
"""
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print("Error summarizing page:", e)
        return "Sorry, I couldn't summarize this page right now."
