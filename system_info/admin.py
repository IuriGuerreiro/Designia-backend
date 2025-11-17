from django.contrib import admin

from .models import AppVersion


@admin.register(AppVersion)
class AppVersionAdmin(admin.ModelAdmin):
    list_display = ["platform", "mandatory_version", "latest_version", "is_active", "updated_at"]
    list_filter = ["platform", "is_active"]
    search_fields = ["platform", "mandatory_version", "latest_version"]
    readonly_fields = ["created_at", "updated_at"]

    fieldsets = (
        ("Version Information", {"fields": ("platform", "mandatory_version", "latest_version")}),
        ("Update Settings", {"fields": ("update_message", "download_url", "is_active")}),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )
