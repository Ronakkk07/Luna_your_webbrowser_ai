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


_CASUAL_RE = re.compile(
    r"^(hi|hello|hey|yo|sup|hiya|how are you|how are u|how're you|how'?s it going|"
    r"how are we|what'?s up|whats up|good (morning|afternoon|evening|night)( luna)?|"
    r"thanks|thank you|thank u|thx|cool|nice|awesome|okay|ok|k|lol|haha|hehe|"
    r"nvm|never ?mind|i love you|love you|miss you|you'?re (funny|great|awesome|the best|sweet)|"
    r"tell me a joke|tell me a story|say something|are you there|you there|"
    r"good (job|girl|boy)|well done|bye|goodbye|see you|good night)\b"
)


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

    # --- casual / small talk → handled by the free chat model (stays "unknown"),
    # checked before the question rule so "how are you" isn't treated as a query.
    if _CASUAL_RE.match(t):
        return result  # intent stays "unknown" -> casual_chat

    # --- time ---
    if re.search(r"\b(what('| i)?s )?the time\b|\bwhat time\b|\bcurrent time\b|\bwhat('| i)?s the date\b", t):
        result["intent"] = "get_time"
        return result

    # --- open a site AND ask about it: "open polymarket and tell me the odds..."
    m = re.match(r"^(?:open|go to|navigate to|launch)\s+(.+?)\s+and\s+(.+)$", t)
    if m and re.search(r"\b(tell|what|whats|what's|give|find|check|show|how|is|are|does)\b", m.group(2)):
        target = m.group(1).strip()
        result["intent"] = "open_and_answer"
        result["query"] = text  # full utterance; the page-answer LLM uses it
        for name, url in KNOWN_SITES.items():
            if name in target:
                result["url"] = url
                break
        if not result["url"]:
            if re.match(r"^[\w.-]+\.\w{2,}$", target):
                result["url"] = "https://" + target
            else:
                result["url"] = "https://" + re.sub(r"\s+", "", target) + ".com"
        return result

    # --- highlight / point to something on the current page ---
    if re.search(r"\bhighlight\b", t) or re.search(r"\bshow me where\b", t):
        result["intent"] = "highlight"
        hm = re.search(r"\b(?:highlight|show me where(?: it says)?)\s+(.+)$", t)
        q = hm.group(1) if hm else text
        # Drop "... on this/the (open) page/tab", leading articles, and trailing
        # filler nouns so "the multi-cloud text" -> "multi-cloud".
        q = re.sub(r"\s+(?:on|in)\s+(?:the\s+|this\s+|current\s+|open\s+|my\s+)*(?:page|screen|site|tab)\b.*$", "", q)
        q = re.sub(r"^(?:the|a|an|that|this|any|some)\s+", "", q)
        q = re.sub(r"\s+(?:text|word|words|phrase|part|section|bit|line|sentence)$", "", q)
        q = q.strip(" .,?!\"'")
        result["query"] = q or text
        return result

    # --- semantic browsing-history search ---
    if (
        re.search(r"\b(browsing history|browser history|my history|in my history|history for)\b", t)
        or re.search(r"\bwhere did i (see|read|find)\b", t)
        or re.search(r"\b(that|the)\s+(article|page|site|website|video|blog|post|recipe|thing)\b.{0,40}?\bi\s+(saw|read|watched|visited|opened|looked at|found)\b", t)
    ):
        result["intent"] = "find_history"
        hm = (
            re.search(r"\babout\s+(.+)$", t)
            or re.search(r"\bfor\s+(.+)$", t)
            or re.search(r"\b(?:see|read|watched|find|visited|opened|looked at)\s+(.+?)(?:\s+in my history|\s+earlier|\s+before|\s+recently|\s+last\b.*)?$", t)
        )
        q = hm.group(1).strip(" ?.\"'") if hm else text
        # Drop a trailing "... i read/saw" so "about gpus i read" -> "gpus".
        q = re.sub(r"\s+i\s+(saw|read|watched|visited|opened|looked at|found)\b.*$", "", q).strip(" ?.\"'")
        result["query"] = q or text
        return result

    # --- question about the page the user is looking at ---
    if re.search(r"\b(this page|this site|current page|current tab|on (the |this )?(page|site|screen|tab)|what does (it|this) say|read (this|it))\b", t):
        result["intent"] = "ask_page"
        result["query"] = text
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
        # Time phrase: "in/after N units", "N units from now", "at 8:30 pm".
        time_re = (
            r"(?:in|after)\s+\d+\s+\w+"
            r"|\d+\s+(?:seconds?|minutes?|hours?|days?|weeks?)(?:\s+from\s+now)?"
            r"|at\s+\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)?"
        )
        dt = re.search(time_re, t)
        if dt:
            result["datetime"] = dt.group(0).strip()
        # Task = what's left after removing "remind me (to)" and the time phrase.
        task = re.sub(r"^.*?\bremind\s+(?:me|us)\s+(?:to\s+)?", "", t)
        task = re.sub(time_re, "", task)
        task = re.sub(r"^\s*to\s+", "", task)  # leftover "to" when time came first
        task = task.strip(" ,.")
        result["task"] = task or text
        return result

    # --- live web research: current/real-time info Gemini can't know ---
    explicit = re.search(r"\b(search (the )?web|look it up|look up|find out|google|research)\b", t)
    live = re.search(
        r"\b(latest|current|currently|today|tonight|right now|this week|this season|"
        r"upcoming|recent|recently|live|scores?|standings?|lineups?|line-?ups?|fixtures?|"
        r"results?|who won|who is winning|who'?s winning|price of|stock|share price|odds|"
        r"betting|weather|forecast|trending|nowadays|as of now|this year)\b",
        t,
    )
    if explicit or live:
        result["intent"] = "web_research"
        q = t
        if explicit:
            q = re.sub(r"^.*?\b(search (the )?web (for )?|look (it )?up|find out|google|research)\b", "", q).strip()
        result["query"] = q or text
        return result

    # --- general question → answer directly ---
    if re.match(r"^(what|who|when|where|why|how|which|is |are |can |could |does |do |explain|tell me|define)\b", t):
        result["intent"] = "answer_question"
        result["query"] = text
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
