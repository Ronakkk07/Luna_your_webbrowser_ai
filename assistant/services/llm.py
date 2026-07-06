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
  "intent": "create_reminder | add_shopping | summarize | list_reminders | list_shopping | open_tab | search_web | play_youtube | switch_tab | close_tab | list_tabs | summarize_page | get_time | get_news | answer_question | unknown",
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
- "answer_question": user asks an informational question or wants an explanation,
  fact, definition, advice, calculation, or general knowledge you can answer
  DIRECTLY (e.g. "what is quantum computing", "who is Ada Lovelace", "how do I
  center a div", "why is the sky blue", "explain X"). Prefer this over search_web —
  only use search_web when the user explicitly wants to open a browser search or
  see results/links. Put the user's full question in "query".
- "search_web": user explicitly wants to search the web / open results in the browser. Put the search terms in "query".
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


def answer_question(text: str) -> str:
    """Answer a general/informational question directly, spoken-friendly."""
    question = (text or "").strip()
    if not question:
        return "What would you like to know?"
    prompt = f"""
You are Luna, a friendly, knowledgeable voice assistant. Answer the user's
question or request directly, as if speaking it aloud.

Rules:
- Be accurate and genuinely informative — actually answer, don't deflect.
- Keep it concise and conversational: usually 1-4 sentences. Expand only if the
  question truly needs it.
- Plain spoken text only — no markdown, headings, bullet points, or links.
- If you're unsure or it needs live/real-time data you don't have, say so briefly
  and offer to look it up.

User: "{question}"

Answer:
"""
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print("Error answering question:", e)
        return "Sorry, I couldn't work that out right now."


def news_briefing(headlines, query=None) -> str:
    """Synthesize a short spoken news briefing from credible headlines.

    ``headlines`` is a list of {'title', 'source', ...} dicts (from Google News,
    which aggregates established outlets). Gemini turns them into a flowing
    2-4 sentence briefing rather than a raw list, and names notable sources.
    """
    if not headlines:
        topic = f" about {query}" if query else ""
        return f"I couldn't find any news{topic} right now."

    lines = "\n".join(
        f"- {h.get('title')} ({h.get('source') or 'unknown'})" for h in headlines
    )
    topic = f" about {query}" if query else " today"
    prompt = f"""
You are Luna, a voice assistant giving a spoken news update. Using ONLY the
credible headlines below (from Google News, which aggregates established
outlets), write a concise, natural spoken briefing of the main news{topic}.

Rules:
- 2 to 4 sentences, flowing prose a person can listen to — NOT a bulleted list.
- Synthesize the main themes; group related stories.
- Mention a couple of notable outlets by name for credibility.
- Do not invent facts beyond the headlines. If they're thin, say so briefly.

Headlines:
{lines}

Return only the spoken briefing text.
"""
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print("Error building news briefing:", e)
        # Fall back to a plain read-out of the titles.
        titles = "; ".join(h.get("title", "") for h in headlines[:4])
        return f"Here's what's in the news: {titles}."


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
