from django.contrib import admin

from .models import UserSettings


@admin.register(UserSettings)
class UserSettingsAdmin(admin.ModelAdmin):
    list_display = ("user", "llm_provider", "has_key", "display_name", "updated_at")
    list_filter = ("llm_provider",)
    search_fields = ("user__username", "display_name")
    readonly_fields = ("api_key_encrypted", "created_at", "updated_at")

    @admin.display(boolean=True, description="Has key")
    def has_key(self, obj):
        return obj.has_key
