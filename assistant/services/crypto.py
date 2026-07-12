"""Symmetric encryption for user-supplied secrets (BYO API keys).

Keys are encrypted at rest with Fernet. The Fernet key is derived from
``LUNA_ENCRYPTION_KEY`` (or ``SECRET_KEY`` as a fallback) so no extra config is
required to get going — but set a dedicated ``LUNA_ENCRYPTION_KEY`` in production
and rotate it independently of the Django secret.
"""
import base64
import hashlib

from django.conf import settings

try:  # cryptography ships with most Django stacks; degrade safely if absent.
    from cryptography.fernet import Fernet, InvalidToken
except Exception:  # pragma: no cover
    Fernet = None

    class InvalidToken(Exception):
        pass


def _fernet():
    if Fernet is None:
        return None
    raw = (getattr(settings, "LUNA_ENCRYPTION_KEY", "") or settings.SECRET_KEY).encode()
    key = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
    return Fernet(key)


def available():
    """True when real encryption is available (cryptography installed)."""
    return Fernet is not None


def encrypt(text):
    """Encrypt a plaintext secret -> token string. Empty in, empty out."""
    text = (text or "").strip()
    if not text:
        return ""
    f = _fernet()
    if f is None:
        # No cryptography: refuse to persist a plaintext secret silently.
        raise RuntimeError(
            "cryptography is not installed — cannot store API keys securely. "
            "Run: pip install cryptography"
        )
    return f.encrypt(text.encode()).decode()


def decrypt(token):
    """Decrypt a token -> plaintext. Returns '' on any failure."""
    token = (token or "").strip()
    if not token:
        return ""
    f = _fernet()
    if f is None:
        return ""
    try:
        return f.decrypt(token.encode()).decode()
    except InvalidToken:
        return ""
