"""Fetch news headlines from Google News RSS (no API key required).

This replaces the decommissioned AWS City Info API as the assistant's
"live external data" source.
"""
from urllib.parse import quote
from xml.etree import ElementTree

import requests
from django.conf import settings


class NewsLookupError(Exception):
    pass


def _clean(text):
    return (text or "").strip()


def fetch_headlines(query=None, limit=5):
    """Return a list of {'title', 'link', 'source'} headline dicts.

    When ``query`` is provided we search Google News; otherwise we pull the
    top stories feed.
    """
    if query:
        url = settings.NEWS_RSS_URL.format(query=quote(_clean(query)))
    else:
        url = settings.NEWS_TOP_RSS_URL

    try:
        response = requests.get(
            url,
            timeout=10,
            headers={"User-Agent": "Luna-Assistant/1.0"},
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise NewsLookupError("News service is unavailable right now.") from exc

    try:
        root = ElementTree.fromstring(response.content)
    except ElementTree.ParseError as exc:
        raise NewsLookupError("News service returned invalid data.") from exc

    headlines = []
    for item in root.iterfind(".//item"):
        title = _clean(item.findtext("title"))
        if not title:
            continue
        source_el = item.find("source")
        headlines.append(
            {
                "title": title,
                "link": _clean(item.findtext("link")),
                "source": _clean(source_el.text) if source_el is not None else "",
            }
        )
        if len(headlines) >= limit:
            break

    return headlines


def summarize_headlines(headlines, query=None):
    """Turn headline dicts into a short spoken summary string."""
    if not headlines:
        topic = f" about {query}" if query else ""
        return f"I couldn't find any news{topic} right now."

    topic = f" about {query}" if query else ""
    lines = [f"Here are the top headlines{topic}:"]
    for index, headline in enumerate(headlines, start=1):
        source = f" — {headline['source']}" if headline.get("source") else ""
        lines.append(f"{index}. {headline['title']}{source}")
    return "\n".join(lines)
