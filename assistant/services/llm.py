import json
import re

from assistant.services import memory, providers


def _fallback_intent(text):
    """When Gemini is unavailable, fall back to local keyword detection so the
    core browser commands keep working offline / under rate limits."""
    from assistant.services.intent import detect_intent

    return detect_intent(text)


# Intents whose *understanding* benefits from Gemini (they extract structured
# fields). Everything else is resolved by the local keyword detector, so obvious
# tasks and casual talk never spend a Gemini call.
_GEMINI_REFINE_INTENTS = {"create_reminder", "add_shopping"}

# References to earlier turns ("open those resources", "read the first one").
_FOLLOWUP_RE = re.compile(
    r"\b(that|those|these|them|it|this one|the ones|the same|again|more|"
    r"the resources?|the links?|the sources?|the articles?|the videos?|"
    r"the first one|the second one|the last one|there)\b"
)


def analyze_intent(text, user_id=None):
    """Local-first intent detection, with context for follow-ups.

    The deterministic keyword detector handles obvious commands, questions, and
    casual talk with no API call. Gemini is used only when there's real value:
    extraction-heavy intents, or a follow-up that references earlier turns.
    """
    local = _fallback_intent(text)  # detect_intent()
    history = memory.history_text(user_id) if user_id is not None else ""

    # A follow-up ("open those resources") must be resolved against the recent
    # conversation, so let the LLM interpret it with that context.
    if history and _FOLLOWUP_RE.search((text or "").lower()):
        return _gemini_analyze_intent(text, fallback=local, history=history, user_id=user_id)

    if local.get("intent") in _GEMINI_REFINE_INTENTS:
        return _gemini_analyze_intent(text, fallback=local, history=history, user_id=user_id)
    return local


def _gemini_analyze_intent(text, fallback=None, history="", user_id=None):
    context_block = ""
    if history:
        context_block = f"""
Recent conversation (for context — resolve references like "it/that/those/the
resources" using this, and put the concrete thing into the fields):
{history}
"""
    prompt = f"""
You are Luna, an intelligent browser voice assistant (like Alexa, but living in the
browser). Extract a structured intent from the user's spoken command below.
{context_block}
Command:
"{text}"

Return ONLY valid JSON in this exact shape:

{{
  "intent": "create_reminder | add_shopping | summarize | list_reminders | list_shopping | open_tab | search_web | play_youtube | web_research | ask_page | open_and_answer | switch_tab | close_tab | list_tabs | summarize_page | highlight | find_history | get_time | get_news | answer_question | unknown",
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
- "highlight": user wants something on the CURRENT page highlighted / pointed to / shown
  (e.g. "highlight the price", "show me where it says refund"). Put the thing to find in "query".
- "find_history": user wants to find a page from their BROWSING HISTORY by meaning
  (e.g. "find that article about GPUs I read", "where did I see the recipe"). Put the topic in "query".
- "get_time": user asks for the current time or date.
- "get_news": user asks for news/headlines. Put a topic in "query" if they name one, else null.
- "create_reminder": put the reminder text in "task" and any time phrase in "datetime".
- "add_shopping": put items in "items".
- Anything conversational or unclear: "unknown".

No explanations. Only JSON.
"""

    if fallback is None:
        fallback = _fallback_intent(text)

    try:
        raw = providers.complete(
            prompt, user_id=user_id, tier="standard", max_tokens=512, temperature=0.2
        ).strip()
    except Exception as e:  # network / API failure / no provider
        print("LLM analyze_intent error:", e)
        return fallback

    # Remove markdown wrapping if present
    cleaned = raw.replace("```json", "").replace("```", "").strip()

    try:
        data = json.loads(cleaned)
    except Exception:
        print("Gemini raw output:", raw)  # Debug
        return fallback

    # Normalise so downstream code can rely on the keys existing.
    for key, default in fallback.items():
        data.setdefault(key, default)
    return data

def casual_chat(transcript: str, history: str = "", user_id=None) -> str:
    """Casual conversation / small talk — always answered by the free model
    (tier='casual') to conserve everyone's key, whether or not they BYO one."""
    system = (
        "You are Luna, a warm, witty AI companion and friend. Reply to casual "
        "conversation naturally and briefly, like a supportive friend would — "
        "1 to 3 sentences, plain spoken text, no markdown or lists. If asked to do "
        "something you can't, say so kindly. Use the conversation so far for context."
    )
    user = transcript
    if history:
        user = f"Conversation so far:\n{history}\n\nUser now says: {transcript}"
    try:
        return providers.chat(
            system, user, user_id=user_id, tier="casual", max_tokens=160, temperature=0.8
        )
    except Exception as e:
        print("casual_chat error:", e)
        return "Sorry, I didn't quite catch that. Could you say it again?"


def answer_question(text: str, history: str = "", user_id=None) -> str:
    """Answer a general/informational question directly, spoken-friendly."""
    question = (text or "").strip()
    if not question:
        return "What would you like to know?"
    context_block = f"\nConversation so far (for context):\n{history}\n" if history else ""
    prompt = f"""
You are Luna — a knowledgeable, warm AI companion talking with a close friend.
Answer the user's question or request thoroughly, the way a smart friend would
explain something they know well, out loud.
{context_block}

Rules:
- Be genuinely informative and give real detail: cover the key points, add useful
  context or an example, and explain the "why", not just a one-liner.
- Aim for about 3 to 6 spoken sentences — enough to actually satisfy the question,
  but still natural to listen to. Go longer only if the topic truly needs it.
- Warm, conversational, friendly tone — like a friend, not a textbook.
- Plain spoken text only — no markdown, headings, bullet points, or links.
- If it needs live/real-time data you don't have, say so briefly and offer to
  look it up.

User: "{question}"

Answer:
"""
    try:
        return providers.complete(prompt, user_id=user_id, tier="complex", max_tokens=768)
    except providers.QuotaExceeded as e:
        return str(e)
    except Exception as e:
        print("Error answering question:", e)
        return "Sorry, I couldn't work that out right now."


def research_answer(query: str, sources, history: str = "", user_id=None) -> str:
    """Answer a live question using web/news sources, spoken-friendly with citations."""
    if not sources:
        return f"I looked, but couldn't find anything current about {query} right now."
    context_block = f"\nConversation so far (for context):\n{history}\n" if history else ""

    blocks = []
    for s in sources:
        block = f"[{s.get('source') or 'source'}] {s.get('title', '')}"
        if s.get("excerpt"):
            block += f"\n{s['excerpt'][:900]}"
        blocks.append(block)
    context = "\n\n".join(blocks)

    prompt = f"""
You are Luna, a companion who just looked something up on the web for a friend.
{context_block}
The user asked: "{query}"

Using the recent results below (from credible outlets), answer their question out
loud with the ACTUAL information — names, numbers, dates, results. Be specific.

Rules:
- 2 to 5 natural spoken sentences. No markdown or lists.
- Mention a source or two by name (e.g. "according to ESPN").
- If the results don't clearly contain the answer, say what you did find and that
  details are still limited — don't make things up.

Results:
{context}

Spoken answer:
"""
    try:
        return providers.complete(prompt, user_id=user_id, tier="complex", max_tokens=640)
    except Exception as e:
        print("Error in research_answer:", e)
        titles = "; ".join(s.get("title", "") for s in sources[:3])
        return f"Here's what I found: {titles}."


def answer_about_page(page_text: str, question: str, title: str = "", user_id=None) -> str:
    """Answer a question using the text of a web page the user is looking at.

    RAG: retrieve the passages most relevant to the question (retrieval.top_passages)
    rather than sending the whole page — cheaper and more accurate on long pages.
    """
    from assistant.services import retrieval

    if not (page_text or "").strip():
        return "There's no readable text on this page for me to check."
    snippet = retrieval.top_passages(page_text, question, k=6, max_chars=8000)
    if not snippet:
        snippet = (page_text or "").strip()[:8000]
    heading = f'Page title: "{title}"\n' if title else ""
    prompt = f"""
You are Luna. The user is looking at a web page and asked: "{question}"

Answer using ONLY the page content below. Pull out the specific details they want
(numbers, odds, names, prices, etc.). If the answer isn't on the page, say you
couldn't find it there.

Rules: 2 to 5 spoken sentences, plain text, no markdown.

{heading}Page content:
\"\"\"
{snippet}
\"\"\"

Spoken answer:
"""
    try:
        return providers.complete(prompt, user_id=user_id, tier="complex", max_tokens=640)
    except Exception as e:
        print("Error in answer_about_page:", e)
        return "Sorry, I couldn't read that page just now."


def news_briefing(headlines, query=None, user_id=None) -> str:
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
        return providers.complete(prompt, user_id=user_id, tier="standard", max_tokens=512)
    except Exception as e:
        print("Error building news briefing:", e)
        # Fall back to a plain read-out of the titles.
        titles = "; ".join(h.get("title", "") for h in headlines[:4])
        return f"Here's what's in the news: {titles}."


def rank_history(query: str, items, user_id=None, top_k=5):
    """Semantically pick the browsing-history items most relevant to ``query``.

    ``items`` is a list of {"title", "url"} (from the extension's chrome.history).
    Returns {"speak": <spoken summary>, "matches": [{"title","url"}, ...]}. Uses the
    free model to match by meaning (not just keywords); can be swapped for embeddings
    later. Falls back to a keyword filter if the model is unavailable.
    """
    query = (query or "").strip()
    items = [it for it in (items or []) if it.get("url")][:80]
    if not items:
        return {"speak": "I couldn't find anything in your history for that.", "matches": []}

    numbered = "\n".join(
        f"{i}. {(it.get('title') or it.get('url'))[:120]} — {it.get('url')[:120]}"
        for i, it in enumerate(items)
    )
    prompt = f"""
The user is searching their browser history for: "{query}"

Below is a numbered list of recently visited pages. Pick the ones that best match
what they're looking for BY MEANING (not just exact words). Return ONLY JSON:

{{"indexes": [<the numbers of the best matches, most relevant first, at most {top_k}>],
  "speak": "<one friendly spoken sentence describing what you found, no markdown>"}}

If nothing fits, return {{"indexes": [], "speak": "<say you couldn't find it>"}}.

Pages:
{numbered}
"""
    try:
        raw = providers.complete(prompt, user_id=user_id, tier="standard", max_tokens=400, temperature=0.2)
        cleaned = raw.replace("```json", "").replace("```", "").strip()
        data = json.loads(cleaned)
        idxs = [i for i in data.get("indexes", []) if isinstance(i, int) and 0 <= i < len(items)][:top_k]
        matches = [{"title": items[i].get("title") or items[i]["url"], "url": items[i]["url"]} for i in idxs]
        speak = (data.get("speak") or "").strip()
        if not speak:
            speak = f"I found {len(matches)} page(s) about {query}." if matches else \
                    f"I couldn't find anything about {query} in your history."
        return {"speak": speak, "matches": matches}
    except Exception as e:
        print("rank_history error:", e)
        # Keyword fallback.
        q = query.lower()
        hits = [it for it in items if q and (q in (it.get("title") or "").lower() or q in it["url"].lower())][:top_k]
        matches = [{"title": it.get("title") or it["url"], "url": it["url"]} for it in hits]
        speak = f"I found {len(matches)} page(s) about {query}." if matches else \
                f"I couldn't find anything about {query} in your history."
        return {"speak": speak, "matches": matches}


def summarize_page_text(text: str, title: str = "", user_id=None) -> str:
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
        return providers.complete(prompt, user_id=user_id, tier="complex", max_tokens=512)
    except Exception as e:
        print("Error summarizing page:", e)
        return "Sorry, I couldn't summarize this page right now."
