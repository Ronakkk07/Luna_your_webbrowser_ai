"""Short-term conversation memory (per user), backed by the cache.

Keeps the last few turns so follow-up questions and tasks have context —
e.g. "open those resources" knows what "those" refers to.

Cache-backed (Redis in production, local-memory in dev) so context is **shared
across web + worker instances** and survives restarts — an in-process deque would
be lost on restart and invisible to other instances, breaking horizontal scale.
This is still lightweight conversation context, not a document store / RAG.
"""
from django.core.cache import cache

_MAX_TURNS = 12  # ~6 exchanges
_TTL = 60 * 60 * 24  # forget a conversation after a day of silence


def _key(user_id):
    return f"convmem:{user_id}"


def add_turn(user_id, role, text):
    text = (text or "").strip()
    if not text or user_id is None:
        return
    turns = cache.get(_key(user_id)) or []
    turns.append({"role": role, "text": text})
    if len(turns) > _MAX_TURNS:
        turns = turns[-_MAX_TURNS:]
    cache.set(_key(user_id), turns, _TTL)


def get_turns(user_id):
    if user_id is None:
        return []
    return cache.get(_key(user_id)) or []


def history_text(user_id, max_turns=8):
    """Recent turns formatted for a prompt, oldest first. Empty if none."""
    turns = get_turns(user_id)[-max_turns:]
    lines = []
    for t in turns:
        who = "User" if t["role"] == "user" else "Luna"
        lines.append(f"{who}: {t['text']}")
    return "\n".join(lines)


def clear(user_id):
    if user_id is not None:
        cache.delete(_key(user_id))
