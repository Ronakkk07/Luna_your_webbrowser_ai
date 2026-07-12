"""LLM provider abstraction — the single entry point for every LLM call.

Routing (implements the owner's cost model):
  * A user who has saved their **own** API key gets their provider (premium quality,
    zero cost to the owner) for standard/complex work.
  * Everyone else — and all casual chat — uses the owner-hosted **free** model
    (Groq free tier, then Hugging Face, then the owner's Gemini as a last resort),
    subject to a per-user daily quota.

Adding a provider = one small class + a line in ``_build`` (open/closed). Callers
never touch provider details; they call ``complete()`` / ``chat()`` with a ``user_id``.
"""
import os

import requests
from django.conf import settings


class LLMError(Exception):
    """No provider could produce a response."""


class QuotaExceeded(LLMError):
    """The user hit their daily free-model cap."""


# --------------------------------------------------------------------------- #
# Providers — each implements .generate(system, user, max_tokens, temperature)  #
# --------------------------------------------------------------------------- #
class _Provider:
    name = "base"

    def generate(self, system, user, max_tokens, temperature):  # pragma: no cover
        raise NotImplementedError


class GeminiProvider(_Provider):
    name = "gemini"

    def __init__(self, api_key, model="models/gemini-2.5-flash"):
        self.api_key = api_key
        self.model_name = model if model.startswith("models/") else f"models/{model}"

    def generate(self, system, user, max_tokens, temperature):
        import google.generativeai as genai

        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel(
            self.model_name,
            system_instruction=system or None,
        )
        resp = model.generate_content(
            user,
            generation_config={
                "max_output_tokens": max_tokens,
                "temperature": temperature,
            },
        )
        text = (getattr(resp, "text", "") or "").strip()
        if not text:
            raise LLMError("gemini returned empty text")
        return text


class GroqProvider(_Provider):
    """Groq's OpenAI-compatible chat API. Free tier is fast and capable."""

    name = "groq"
    ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, api_key, model="llama-3.3-70b-versatile"):
        self.api_key = api_key
        self.model_name = model

    def generate(self, system, user, max_tokens, temperature):
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        resp = requests.post(
            self.ENDPOINT,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model_name,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            timeout=30,
        )
        resp.raise_for_status()
        text = (resp.json()["choices"][0]["message"]["content"] or "").strip()
        if not text:
            raise LLMError("groq returned empty text")
        return text


class HFProvider(_Provider):
    """Wraps the existing Hugging Face inference client (hf.py)."""

    name = "hf"

    def generate(self, system, user, max_tokens, temperature):
        from assistant.services.hf import hf_chat

        text = hf_chat(system, user, max_tokens=max_tokens, temperature=temperature)
        if not text:
            raise LLMError("hf returned nothing / not configured")
        return text


class OpenAIProvider(_Provider):
    """OpenAI-compatible chat API (for users who BYO an OpenAI key)."""

    name = "openai"
    ENDPOINT = "https://api.openai.com/v1/chat/completions"

    def __init__(self, api_key, model="gpt-4o-mini"):
        self.api_key = api_key
        self.model_name = model

    def generate(self, system, user, max_tokens, temperature):
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        resp = requests.post(
            self.ENDPOINT,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model_name,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            timeout=30,
        )
        resp.raise_for_status()
        text = (resp.json()["choices"][0]["message"]["content"] or "").strip()
        if not text:
            raise LLMError("openai returned empty text")
        return text


_BYO_BUILDERS = {
    "gemini": lambda key: GeminiProvider(key, getattr(settings, "GEMINI_MODEL", "models/gemini-2.5-flash")),
    "groq": lambda key: GroqProvider(key, getattr(settings, "GROQ_MODEL", "llama-3.3-70b-versatile")),
    "openai": lambda key: OpenAIProvider(key, getattr(settings, "OPENAI_MODEL", "gpt-4o-mini")),
}


# --------------------------------------------------------------------------- #
# Free provider — tries several owner-hosted free backends in order            #
# --------------------------------------------------------------------------- #
class FreeProvider(_Provider):
    name = "free"

    def _backends(self):
        chain = []
        groq_key = getattr(settings, "GROQ_API_KEY", "") or ""
        if groq_key:
            chain.append(GroqProvider(groq_key, getattr(settings, "GROQ_MODEL", "llama-3.3-70b-versatile")))
        # HFProvider self-checks its token inside hf.py.
        chain.append(HFProvider())
        gem_key = getattr(settings, "GEMINI_API_KEY", "") or ""
        if gem_key and getattr(settings, "FREE_LLM_ALLOW_OWNER_GEMINI", True):
            chain.append(GeminiProvider(gem_key, getattr(settings, "GEMINI_MODEL", "models/gemini-2.5-flash")))
        return chain

    def generate(self, system, user, max_tokens, temperature):
        last = None
        for backend in self._backends():
            try:
                return backend.generate(system, user, max_tokens, temperature)
            except Exception as exc:  # try the next free backend
                last = exc
                print(f"free provider '{backend.name}' failed:", exc)
        raise LLMError(f"no free provider available ({last})")


# --------------------------------------------------------------------------- #
# Selection + public API                                                       #
# --------------------------------------------------------------------------- #
def _user_settings(user_id):
    if user_id is None:
        return None
    try:
        from assistant.models import UserSettings

        return UserSettings.objects.filter(user_id=user_id).first()
    except Exception:
        return None


def pick(user_id, tier):
    """Return (provider, is_free) for this user + tier.

    Casual talk always uses the free model (to conserve everyone's key). For
    standard/complex work, a user with their own key uses it; otherwise free.
    """
    if tier != "casual":
        us = _user_settings(user_id)
        if us and us.has_key:
            builder = _BYO_BUILDERS.get(us.llm_provider or "gemini")
            if builder:
                key = us.get_api_key()
                if key:
                    return builder(key), False
    return FreeProvider(), True


def _run(user_id, tier, system, user, max_tokens, temperature):
    provider, is_free = pick(user_id, tier)
    if is_free:
        from assistant.services import quota

        if not quota.allow(user_id):
            raise QuotaExceeded(
                "You've reached today's free usage limit. Add your own API key "
                "in Luna's settings for unlimited use."
            )
    return provider.generate(system, user, max_tokens, temperature)


def complete(prompt, *, user_id=None, tier="standard", max_tokens=768, temperature=0.7):
    """One-shot completion from a single prompt. Raises LLMError on failure."""
    return _run(user_id, tier, "", prompt, max_tokens, temperature)


def chat(system, user, *, user_id=None, tier="standard", max_tokens=256, temperature=0.7):
    """System + user chat completion. Raises LLMError on failure."""
    return _run(user_id, tier, system, user, max_tokens, temperature)
