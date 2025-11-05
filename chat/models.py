from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Chat(models.Model):
    """
    Chat model for 1-on-1 conversations between two users
    """

    user1 = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chats_as_user1")
    user2 = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chats_as_user2")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Track last message for efficient querying
    last_message = models.ForeignKey("Message", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        # Ensure unique chat between two users (regardless of order)
        unique_together = [["user1", "user2"]]
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["user1", "user2"]),
            models.Index(fields=["-updated_at"]),
        ]

    def clean(self):
        """Validate that user1 and user2 are different users"""
        if self.user1 == self.user2:
            raise ValidationError("Users cannot chat with themselves")

    def save(self, *args, **kwargs):
        self.full_clean()
        # Ensure user1.id < user2.id for consistent ordering
        if self.user1.id > self.user2.id:
            self.user1, self.user2 = self.user2, self.user1
        super().save(*args, **kwargs)

    def get_other_user(self, current_user):
        """Get the other user in the chat"""
        return self.user2 if self.user1 == current_user else self.user1

    def has_user(self, user):
        """Check if user is part of this chat"""
        return user == self.user1 or user == self.user2

    @classmethod
    def get_or_create_chat(cls, user1, user2):
        """Get or create a chat between two users"""
        if user1.id > user2.id:
            user1, user2 = user2, user1

        chat, created = cls.objects.get_or_create(user1=user1, user2=user2)
        return chat, created

    def __str__(self):
        return f"Chat between {self.user1.username} and {self.user2.username}"


class Message(models.Model):
    """
    Message model supporting text and image messages
    """

    MESSAGE_TYPE_CHOICES = [
        ("text", "Text"),
        ("image", "Image"),
    ]

    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    # Message content
    message_type = models.CharField(max_length=10, choices=MESSAGE_TYPE_CHOICES, default="text")
    text_content = models.TextField(blank=True, null=True)

    # Image content (S3 storage)
    image_url = models.CharField(max_length=500, blank=True, null=True, help_text="S3 object key for image")
    image_temp_url = models.URLField(blank=True, null=True, help_text="Temporary S3 URL (generated on request)")

    # Message metadata
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["chat", "created_at"]),
            models.Index(fields=["sender", "created_at"]),
            models.Index(fields=["is_read"]),
        ]

    def clean(self):
        """Validate message content"""
        if self.message_type == "text" and not self.text_content:
            raise ValidationError("Text messages must have text content")
        if self.message_type == "image" and not self.image_url:
            raise ValidationError("Image messages must have image URL")

        # Ensure sender is part of the chat
        if not self.chat.has_user(self.sender):
            raise ValidationError("Sender must be part of the chat")

    def save(self, *args, **kwargs):
        self.full_clean()
        is_new = self.pk is None

        super().save(*args, **kwargs)

        # Update chat's last_message and updated_at
        if is_new:
            self.chat.last_message = self
            self.chat.save(update_fields=["last_message", "updated_at"])

            # Note: Activity WebSocket notifications are handled in chat/views.py for better control

    def get_image_temp_url(self, expires_in: int = 3600) -> str:
        """Generate temporary URL for image if it exists in S3"""
        if not self.image_url:
            return None

        try:
            from django.conf import settings

            if not getattr(settings, "USE_S3", False):
                return None

            from utils.s3_storage import get_s3_storage

            s3_storage = get_s3_storage()
            return s3_storage.get_file_url(self.image_url, expires_in=expires_in)
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to generate temp URL for message image {self.image_url}: {str(e)}")
            return None

    def mark_as_read(self, reading_user=None):
        """Mark message as read"""
        if not self.is_read:
            from django.utils import timezone

            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at"])

            # Note: Activity WebSocket notifications are handled in chat/views.py for better control

    def __str__(self):
        if self.message_type == "text":
            content_preview = self.text_content[:50] + "..." if len(self.text_content) > 50 else self.text_content
            return f"{self.sender.username}: {content_preview}"
        else:
            return f"{self.sender.username}: [Image]"
