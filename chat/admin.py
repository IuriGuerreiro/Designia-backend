from django.contrib import admin

from .models import Chat, Message


@admin.register(Chat)
class ChatAdmin(admin.ModelAdmin):
    list_display = ("id", "user1", "user2", "created_at", "updated_at")
    list_filter = ("created_at", "updated_at")
    search_fields = ("user1__username", "user1__email", "user2__username", "user2__email")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("id", "chat", "sender", "message_type", "created_at", "is_read")
    list_filter = ("message_type", "is_read", "created_at")
    search_fields = ("sender__username", "sender__email", "text_content")
    readonly_fields = ("created_at",)
