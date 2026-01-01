from django.contrib import admin
from django.utils.html import format_html

from .domain.models import ChatReport, Thread, ThreadMessage, ThreadParticipant
from .models import Chat, Message


# --- Legacy Models ---
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


# --- Refactored Domain Models ---


class ThreadParticipantInline(admin.TabularInline):
    model = ThreadParticipant
    extra = 0
    readonly_fields = ("joined_at", "last_read_at")


class ThreadMessageInline(admin.TabularInline):
    model = ThreadMessage
    extra = 0
    fields = ("sender", "message_type", "text", "image_url", "created_at", "is_read")
    readonly_fields = ("created_at",)
    ordering = ("created_at",)


@admin.register(Thread)
class ThreadAdmin(admin.ModelAdmin):
    list_display = ("id", "is_group", "display_participants", "created_at", "updated_at")
    list_filter = ("is_group", "created_at", "updated_at")
    search_fields = ("id", "participants__username", "participants__email")
    inlines = [ThreadParticipantInline, ThreadMessageInline]
    readonly_fields = ("id", "created_at", "updated_at", "chat_transcript")

    def display_participants(self, obj):
        return ", ".join([p.username for p in obj.participants.all()])

    display_participants.short_description = "Participants"

    def chat_transcript(self, obj):
        messages = obj.messages.all().order_by("created_at")
        if not messages.exists():
            return "No messages in this thread."

        html = [
            "<div style='background: #f8f9fa; padding: 15px; border-radius: 8px; border: 1px solid #dee2e6; max-height: 500px; overflow-y: auto;'>"
        ]
        for msg in messages:
            sender = msg.sender.username
            time = msg.created_at.strftime("%Y-%m-%d %H:%M")

            style = "margin-bottom: 10px; padding: 8px; border-radius: 5px; background: white; border-left: 4px solid #007bff;"

            content = f"<b>{sender}</b> <small style='color: #6c757d;'>({time})</small><br/>"
            if msg.message_type == "text":
                content += f"<span style='white-space: pre-wrap;'>{msg.text}</span>"
            else:
                content += f"<a href='{msg.image_url}' target='_blank'>[View Image]</a>"

            html.append(f"<div style='{style}'>{content}</div>")

        html.append("</div>")
        return format_html("".join(html))

    chat_transcript.short_description = "Full Transcript"


@admin.register(ChatReport)
class ChatReportAdmin(admin.ModelAdmin):
    list_display = ("id", "reporter", "reported_user", "reason", "created_at", "resolved")
    list_filter = ("reason", "resolved", "created_at")
    search_fields = ("reporter__username", "message__sender__username", "description")
    readonly_fields = ("id", "created_at", "message_context")
    actions = ["mark_resolved"]

    def reported_user(self, obj):
        return obj.message.sender.username

    reported_user.short_description = "Reported User"

    def message_context(self, obj):
        msg = obj.message
        thread_url = f"/admin/chat/thread/{msg.thread.id}/change/"
        return format_html(
            "<strong>Message ID:</strong> {}<br/>"
            "<strong>Sender:</strong> {}<br/>"
            "<strong>Content:</strong> {}<br/>"
            "<hr/>"
            "<a href='{}' class='button'>View Full Thread Transcript</a>",
            msg.id,
            msg.sender.username,
            msg.text if msg.message_type == "text" else "[Image]",
            thread_url,
        )

    message_context.short_description = "Message Context"

    def mark_resolved(self, request, queryset):
        queryset.update(resolved=True, resolved_by=request.user)

    mark_resolved.short_description = "Mark selected reports as resolved"
