"""Free Hugging Face LLM client (for casual conversation / light replies).

Keeps Gemini quota for complex work. Every function fails soft: if there's no
token, the library is missing, or the request errors, it returns None and the
caller falls back to Gemini.
"""
from django.conf import settings

try:
    from huggingface_hub import InferenceClient
except Exception:  # library not installed
    InferenceClient = None

_client = None
_client_key = None


def _get_client():
    """Return a cached InferenceClient, or None if HF isn't configured."""
    global _client, _client_key
    token = getattr(settings, "HF_API_TOKEN", "") or ""
    if not token or InferenceClient is None:
        return None
    if _client is None or _client_key != token:
        try:
            _client = InferenceClient(token=token)
            _client_key = token
        except Exception as exc:
            print("HF client init failed:", exc)
            return None
    return _client


def hf_chat(system, user, max_tokens=256, temperature=0.7):
    """Return the model's reply text, or None on any failure."""
    client = _get_client()
    if client is None:
        return None
    model = getattr(settings, "HF_MODEL", "") or "Qwen/Qwen2.5-7B-Instruct"
    try:
        resp = client.chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        text = (resp.choices[0].message.content or "").strip()
        return text or None
    except Exception as exc:
        print("HF chat error:", exc)
        return None


def is_configured():
    return _get_client() is not None
