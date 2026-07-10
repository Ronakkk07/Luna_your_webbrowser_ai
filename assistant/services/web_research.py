"""Live web research: for questions that need current/real-time info (scores,
"latest", upcoming events, etc.) that Gemini's training data can't answer.

Keyless and reliable: it queries Google News (which aggregates credible outlets),
best-effort fetches a couple of article pages for depth, and the caller has Gemini
synthesize a spoken answer with sources.
"""
import re
from html import unescape

import requests

from assistant.services.news import fetch_headlines

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def _strip_html(html):
    html = re.sub(r"(?is)<(script|style|noscript|header|footer|nav|svg)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def fetch_article_text(url, limit=1500):
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=8, allow_redirects=True)
        resp.raise_for_status()
        return _strip_html(resp.text)[:limit]
    except requests.RequestException:
        return ""


def gather(query, max_sources=5, fetch_pages=2):
    """Return a list of {'title','source','excerpt'} for the query."""
    try:
        headlines = fetch_headlines(query=query, limit=max_sources)
    except Exception:
        headlines = []

    sources = []
    for i, h in enumerate(headlines):
        excerpt = ""
        if i < fetch_pages and h.get("link"):
            excerpt = fetch_article_text(h["link"])
        sources.append(
            {
                "title": h.get("title", ""),
                "source": h.get("source", ""),
                "excerpt": excerpt,
            }
        )
    return sources
