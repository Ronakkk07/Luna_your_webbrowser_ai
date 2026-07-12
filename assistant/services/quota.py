"""Per-user daily quota for the free (owner-hosted) model.

Keyless users share the owner's free-tier model, so they get a daily cap to keep
cost/abuse bounded. Users who bring their own key are never limited here.

Backed by the Django cache (Redis in production, local-memory in dev). A quota of
0 means unlimited — the default, so nothing is blocked until you choose to enforce.
"""
from datetime import date

from django.conf import settings
from django.core.cache import cache


def _limit():
    return int(getattr(settings, "FREE_LLM_DAILY_QUOTA", 0) or 0)


def _key(user_id):
    return f"llmquota:{user_id}:{date.today().isoformat()}"


def allow(user_id):
    """Reserve one free-model call for ``user_id`` today. False if over the cap."""
    limit = _limit()
    if limit <= 0 or user_id is None:
        return True  # unlimited / anonymous internal call
    key = _key(user_id)
    used = cache.get(key)
    if used is None:
        # First call today: seed with a ~26h TTL so it rolls over daily.
        cache.set(key, 1, 60 * 60 * 26)
        return True
    if used >= limit:
        return False
    try:
        cache.incr(key)
    except ValueError:  # key expired between get and incr
        cache.set(key, 1, 60 * 60 * 26)
    return True


def remaining(user_id):
    """How many free calls the user has left today (None = unlimited)."""
    limit = _limit()
    if limit <= 0:
        return None
    return max(0, limit - (cache.get(_key(user_id)) or 0))
