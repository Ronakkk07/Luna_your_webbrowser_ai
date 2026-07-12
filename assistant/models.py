from django.conf import settings
from django.db import models

from assistant.services import crypto


class UserSettings(models.Model):
    """Per-user assistant preferences, including an optional bring-your-own API key.

    The API key is encrypted at rest (see services/crypto.py) and only decrypted
    at call time by the provider layer. Users without a key fall back to the
    owner-hosted free model.
    """

    PROVIDER_CHOICES = [
        ("gemini", "Google Gemini"),
        ("groq", "Groq"),
        ("openai", "OpenAI"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assistant_settings",
    )
    llm_provider = models.CharField(max_length=20, blank=True, default="")
    api_key_encrypted = models.TextField(blank=True, default="")
    display_name = models.CharField(max_length=80, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"UserSettings({self.user_id})"

    @property
    def has_key(self):
        return bool(self.api_key_encrypted)

    def set_api_key(self, raw):
        """Encrypt and store a plaintext key. Empty clears it."""
        raw = (raw or "").strip()
        self.api_key_encrypted = crypto.encrypt(raw) if raw else ""

    def get_api_key(self):
        return crypto.decrypt(self.api_key_encrypted)
