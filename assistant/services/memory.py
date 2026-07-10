"""Short-term conversation memory (per user).

Keeps the last few turns so follow-up questions and tasks have context —
e.g. "open those resources" knows what "those" refers to. This is deliberately
lightweight (in-process); it's conversation context, not a document store / RAG.
"""
from collections import defaultdict, deque
from threading import Lock

_MAX_TURNS = 12  # ~6 exchanges
_history = defaultdict(lambda: deque(maxlen=_MAX_TURNS))
_lock = Lock()


def add_turn(user_id, role, text):
    text = (text or "").strip()
    if not text:
        return
    with _lock:
        _history[user_id].append({"role": role, "text": text})


def get_turns(user_id):
    with _lock:
        return list(_history[user_id])


def history_text(user_id, max_turns=8):
    """Recent turns formatted for a prompt, oldest first. Empty if none."""
    turns = get_turns(user_id)[-max_turns:]
    lines = []
    for t in turns:
        who = "User" if t["role"] == "user" else "Luna"
        lines.append(f"{who}: {t['text']}")
    return "\n".join(lines)


def clear(user_id):
    with _lock:
        _history.pop(user_id, None)
