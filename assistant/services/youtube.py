"""Resolve a YouTube search query to the first actual video, so the assistant
can *play* a video (open a /watch URL) instead of just showing search results.

Uses a keyless technique: fetch the results page and pull the first videoId out
of the embedded ytInitialData. No API key required.
"""
import re
from urllib.parse import quote_plus

import requests

_VIDEO_ID_RE = re.compile(r'"videoId":"([\w-]{11})"')
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def search_url(query):
    return f"https://www.youtube.com/results?search_query={quote_plus(query)}"


def first_video_url(query):
    """Return a https://www.youtube.com/watch?v=... URL for the top result, or
    None if it can't be resolved."""
    query = (query or "").strip()
    if not query:
        return None
    try:
        resp = requests.get(search_url(query), headers=_HEADERS, timeout=10)
        resp.raise_for_status()
    except requests.RequestException:
        return None

    match = _VIDEO_ID_RE.search(resp.text)
    if not match:
        return None
    return f"https://www.youtube.com/watch?v={match.group(1)}"
