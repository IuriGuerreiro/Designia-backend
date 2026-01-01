import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Thread(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # M2M through explicit model for extra metadata
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through="ThreadParticipant", related_name="threads"
    )

    is_group = models.BooleanField(default=False)
    name = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["-updated_at"]),
        ]

    def __str__(self):
        return f"Thread {self.id} ({'Group' if self.is_group else 'Private'})"


class ThreadParticipant(models.Model):
    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name="thread_participants")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="thread_participations")
    joined_at = models.DateTimeField(auto_now_add=True)
    last_read_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ("thread", "user")


class ThreadMessage(models.Model):
    MESSAGE_TYPE_CHOICES = [
        ("text", "Text"),
        ("image", "Image"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_messages")

    # Content
    message_type = models.CharField(max_length=10, choices=MESSAGE_TYPE_CHOICES, default="text")
    text = models.TextField(
        blank=True, null=True
    )  # Renamed from text_content for simplicity, or keep same? Story said 'text'.

    # Image content (keeping compatibility)
    image_url = models.CharField(max_length=500, blank=True, null=True, help_text="S3 object key for image")

    # Meta
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)  # Legacy field, though Participant.last_read_at is better

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["thread", "created_at"]),
        ]

    def __str__(self):
        return f"Message {self.id} from {self.sender}"


class ChatReport(models.Model):
    REPORT_REASON_CHOICES = [
        ("spam", "Spam"),
        ("harassment", "Harassment"),
        ("inappropriate", "Inappropriate Content"),
        ("scam", "Scam"),
        ("other", "Other"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey(ThreadMessage, on_delete=models.CASCADE, related_name="reports")
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_reports")
    reason = models.CharField(max_length=20, choices=REPORT_REASON_CHOICES)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_reports",
    )
    resolution_note = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["resolved"]),
        ]

    def __str__(self):
        return f"Report {self.id} by {self.reporter} on {self.message}"
