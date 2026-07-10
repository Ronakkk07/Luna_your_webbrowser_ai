"""Turn a structured intent into an action plan for the browser extension.

Every handler returns a dict of the shape::

    {"speak": "<text Luna says>", "actions": [<browser action>, ...]}

Browser actions are executed by the extension's background service worker.
Supported action types (see extension/background.js):

    {"type": "open_tab",       "url": "https://..."}
    {"type": "search_web",     "query": "...", "url": "<fallback search url>"}
    {"type": "switch_tab",     "hint": "gmail"}
    {"type": "close_tab",      "hint": "youtube" | null}   # null = current tab
    {"type": "list_tabs"}
    {"type": "summarize_page"}
"""
from urllib.parse import quote_plus

from django.conf import settings
from django.utils import timezone

try:  # zoneinfo is stdlib on py3.9+
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

from assistant.services.llm import (
    answer_about_page,
    answer_question,
    casual_chat,
    news_briefing,
    research_answer,
)
from assistant.services.news import NewsLookupError, fetch_headlines, summarize_headlines
from assistant.services.youtube import first_video_url, search_url as youtube_search_url
from reminders.tasks import build_reminder_datetime, create_reminder_for_user
from shopping.tasks import add_shopping_items_for_user


def _plan(speak, actions=None):
    return {"speak": speak, "actions": actions or []}


def _search_url(query):
    return f"https://www.google.com/search?q={quote_plus(query)}"


def _handle_create_reminder(data, user):
    task_name = data.get("task") or "General reminder"
    dt = build_reminder_datetime(data.get("datetime"))
    reminder = create_reminder_for_user(user=user, task_name=task_name, dt=dt)
    return _plan(
        f"Reminder set: {reminder.task} at "
        f"{reminder.date_time.strftime('%A %I:%M %p')}."
    )


def _handle_add_shopping(data, user):
    added_items = add_shopping_items_for_user(user, data.get("items", []))
    if added_items:
        return _plan(f"Added to your shopping list: {', '.join(added_items)}.")
    return _plan("Those items are already on your shopping list.")


def _handle_list_shopping(user):
    items = user.shopping_items.all()
    if items.exists():
        listed = ", ".join(f"{item.item_name} ({item.quantity})" for item in items)
        return _plan(f"Your shopping list: {listed}.")
    return _plan("Your shopping list is empty.")


def _handle_list_reminders(user):
    reminders = user.reminders.all()
    if reminders.exists():
        listed = ", ".join(
            f"{r.task} at {r.date_time.strftime('%A %I:%M %p')}" for r in reminders
        )
        return _plan(f"Your reminders: {listed}.")
    return _plan("You have no reminders.")


def _handle_open_tab(data):
    url = (data.get("url") or "").strip()
    if url:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        return _plan(f"Opening {url}.", [{"type": "open_tab", "url": url}])

    query = (data.get("query") or data.get("task") or "").strip()
    if query:
        return _plan(
            f"Searching for {query}.",
            [{"type": "search_web", "query": query, "url": _search_url(query)}],
        )
    return _plan("Which site would you like me to open?")


def _handle_play_youtube(data):
    query = (data.get("query") or data.get("task") or "").strip()
    if not query:
        return _plan(
            "Opening YouTube.",
            [{"type": "open_tab", "url": "https://www.youtube.com"}],
        )

    # Resolve the top result server-side so we can open the actual /watch page.
    # Either way we return a `youtube_play` action; the extension opens the URL
    # and injects a script to press play (or click the first result on a search).
    watch_url = first_video_url(query)
    if watch_url:
        return _plan(
            f"Playing {query} on YouTube.",
            [{"type": "youtube_play", "query": query, "url": watch_url, "kind": "watch"}],
        )
    return _plan(
        f"Playing the top result for {query} on YouTube.",
        [{"type": "youtube_play", "query": query, "url": youtube_search_url(query), "kind": "search"}],
    )


def _handle_search_web(data):
    query = (data.get("query") or data.get("task") or "").strip()
    if not query:
        return _plan("What would you like me to search for?")
    return _plan(
        f"Searching the web for {query}.",
        [{"type": "search_web", "query": query, "url": _search_url(query)}],
    )


def _handle_switch_tab(data):
    hint = (data.get("tab_hint") or data.get("query") or "").strip()
    if not hint:
        return _plan("Which tab should I switch to?")
    return _plan(f"Switching to the {hint} tab.", [{"type": "switch_tab", "hint": hint}])


def _handle_close_tab(data):
    hint = (data.get("tab_hint") or "").strip() or None
    speak = f"Closing the {hint} tab." if hint else "Closing this tab."
    return _plan(speak, [{"type": "close_tab", "hint": hint}])


def _handle_get_time():
    tz = None
    if ZoneInfo is not None:
        try:
            tz = ZoneInfo(settings.ASSISTANT_TIMEZONE)
        except Exception:
            tz = None
    now = timezone.localtime(timezone.now(), tz) if tz else timezone.now()
    return _plan(now.strftime("It's %I:%M %p on %A, %B %d.").replace(" 0", " "))


def _handle_get_news(data):
    query = (data.get("query") or "").strip() or None
    try:
        headlines = fetch_headlines(query=query, limit=8)
    except NewsLookupError:
        return _plan("I couldn't reach the news service right now.")
    # Synthesize a credible spoken briefing rather than reading raw headlines.
    return _plan(news_briefing(headlines, query=query))


def route_intent(data, user):
    """Dispatch a structured intent to a handler, returning an action plan dict."""
    from assistant.services import memory

    intent = data.get("intent")
    task = (data.get("task") or "").lower()
    transcript = data.get("task")
    history = memory.history_text(getattr(user, "id", None))

    if intent == "create_reminder":
        return _handle_create_reminder(data, user)

    if intent == "add_shopping":
        return _handle_add_shopping(data, user)

    if intent == "list_shopping" or (intent == "summarize" and "shopping" in task):
        return _handle_list_shopping(user)

    if intent == "list_reminders" or (intent == "summarize" and "reminder" in task):
        return _handle_list_reminders(user)

    if intent == "open_tab":
        return _handle_open_tab(data)

    if intent == "play_youtube":
        return _handle_play_youtube(data)

    if intent == "search_web":
        return _handle_search_web(data)

    if intent == "switch_tab":
        return _handle_switch_tab(data)

    if intent == "close_tab":
        return _handle_close_tab(data)

    if intent == "list_tabs":
        return _plan("Here are your open tabs.", [{"type": "list_tabs"}])

    if intent == "summarize_page":
        return _plan("Let me read this page for you.", [{"type": "summarize_page"}])

    if intent == "get_time":
        return _handle_get_time()

    if intent == "get_news":
        return _handle_get_news(data)

    if intent == "web_research":
        query = data.get("query") or data.get("_text") or transcript or ""
        from assistant.services.web_research import gather
        return _plan(research_answer(query, gather(query), history=history))

    if intent == "ask_page":
        # The extension reads the current tab and answers the question about it.
        question = data.get("query") or data.get("_text") or transcript or ""
        return _plan("", [{"type": "read_page", "question": question}])

    if intent == "open_and_answer":
        url = (data.get("url") or "").strip()
        question = data.get("query") or data.get("_text") or transcript or ""
        if not url:
            return _plan("Which site should I open?")
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        return _plan(
            "One moment, let me open that and check.",
            [{"type": "open_and_answer", "url": url, "question": question}],
        )

    if intent == "answer_question":
        return _plan(answer_question(data.get("_text") or data.get("query") or transcript or "", history=history))

    if intent in ("unknown", "chitchat"):
        return _plan(casual_chat(data.get("_text") or transcript or "", history=history))

    return _plan("Sorry, I didn't understand that command.")
