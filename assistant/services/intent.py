"""Lightweight keyword-based intent detection.

This is a local, dependency-free backstop used when the Gemini LLM is
unavailable or rate-limited. It won't be as flexible as the LLM, but it keeps
the core browser commands working offline.
"""
import re

# Common "open <site>" shortcuts -> canonical URL.
KNOWN_SITES = {
    "youtube": "https://www.youtube.com",
    "gmail": "https://mail.google.com",
    "google": "https://www.google.com",
    "maps": "https://maps.google.com",
    "github": "https://github.com",
    "twitter": "https://twitter.com",
    "x": "https://x.com",
    "reddit": "https://www.reddit.com",
    "amazon": "https://www.amazon.com",
    "netflix": "https://www.netflix.com",
    "wikipedia": "https://www.wikipedia.org",
    "linkedin": "https://www.linkedin.com",
    "facebook": "https://www.facebook.com",
    "instagram": "https://www.instagram.com",
}


def _blank():
    return {
        "intent": "unknown",
        "task": None,
        "datetime": None,
        "items": [],
        "query": None,
        "url": None,
        "tab_hint": None,
    }


def detect_intent(text):
    """Best-effort structured intent from raw text using keyword rules."""
    result = _blank()
    result["task"] = text
    t = (text or "").lower().strip()

    if not t:
        return result

    # --- time ---
    if re.search(r"\b(what('| i)?s )?the time\b|\bwhat time\b|\bcurrent time\b|\bwhat('| i)?s the date\b", t):
        result["intent"] = "get_time"
        return result

    # --- news ---
    if re.search(r"\bnews\b|\bheadlines?\b", t):
        result["intent"] = "get_news"
        m = re.search(r"(?:news|headlines?)\s+(?:about|on|for)\s+(.+)", t)
        if m:
            result["query"] = m.group(1).strip()
        return result

    # --- tabs ---
    if re.search(r"\b(list|show|what).*tabs?\b|\btabs?\b.*\bopen\b", t):
        result["intent"] = "list_tabs"
        return result

    if re.search(r"\bswitch\b.*\btab\b|\bgo to\b.*\btab\b|\bswitch to\b", t):
        result["intent"] = "switch_tab"
        m = re.search(r"(?:switch to|go to)\s+(?:the\s+)?(.+?)(?:\s+tab)?$", t)
        if m:
            result["tab_hint"] = m.group(1).strip()
        return result

    if re.search(r"\bclose\b.*\btab\b", t):
        result["intent"] = "close_tab"
        m = re.search(r"close\s+(?:the\s+)?(.+?)\s+tab", t)
        if m and m.group(1).strip() not in ("this", "current"):
            result["tab_hint"] = m.group(1).strip()
        return result

    # --- summarize current page ---
    if re.search(r"\b(summari[sz]e|read)\b.*\bpage\b|\bwhat('| i)?s (on )?this page\b", t):
        result["intent"] = "summarize_page"
        return result

    # --- play something on YouTube ---
    if "youtube" in t and re.search(r"\b(play|watch)\b", t):
        result["intent"] = "play_youtube"
        # Pull out the thing to play, dropping filler like "on youtube".
        m = re.search(r"\b(?:play|watch)\b\s+(.+)", t)
        if m:
            q = m.group(1)
            q = re.sub(r"\b(a video of|a video|videos of|the video|some|on youtube|in youtube|from youtube|youtube)\b", "", q)
            result["query"] = q.strip(" ,.")
        return result

    # --- open a site ---
    open_match = re.search(r"\b(open|go to|navigate to|launch)\b\s+(.+)", t)
    if open_match:
        target = open_match.group(2).strip().rstrip(".")
        for name, url in KNOWN_SITES.items():
            if name in target:
                result["intent"] = "open_tab"
                result["url"] = url
                return result
        # A bare domain like "open example.com"
        if re.match(r"^[\w.-]+\.\w{2,}$", target):
            result["intent"] = "open_tab"
            result["url"] = "https://" + target
            return result
        result["intent"] = "search_web"
        result["query"] = target
        return result

    # --- search ---
    search_match = re.search(r"\b(search|google|look up|find)\b\s+(?:for\s+)?(.+)", t)
    if search_match:
        result["intent"] = "search_web"
        result["query"] = search_match.group(2).strip()
        return result

    # --- reminders ---
    if "remind" in t:
        result["intent"] = "create_reminder"
        m = re.search(r"remind me to\s+(.+?)(?:\s+in\s+.+|\s+at\s+.+)?$", t)
        result["task"] = m.group(1).strip() if m else text
        dt = re.search(r"\b(in\s+\d+\s+\w+|at\s+[\w:.\s]+)$", t)
        if dt:
            result["datetime"] = dt.group(1).strip()
        return result

    # --- shopping ---
    if "shopping" in t and ("add" in t or "buy" in t):
        result["intent"] = "add_shopping"
        m = re.search(r"add\s+(.+?)\s+to", t)
        if m:
            items = re.split(r"\s*,\s*|\s+and\s+", m.group(1))
            result["items"] = [i.strip() for i in items if i.strip()]
        return result

    return result  # unknown
