from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.core.paginator import Paginator

from chat.domain.models import Thread, ThreadMessage, ThreadParticipant


class ChatService:
    def __init__(self):
        self.channel_layer = get_channel_layer()

    def send_message(self, user, thread_id, text, image_url=None):
        """
        Persist a message and broadcast it to the thread's group.
        """
        # 1. Validation
        try:
            thread = Thread.objects.get(id=thread_id)
        except Thread.DoesNotExist:
            raise ObjectDoesNotExist("Thread not found")

        if not ThreadParticipant.objects.filter(thread=thread, user=user).exists():
            raise PermissionDenied("User is not a participant of this thread")

        # 2. Persistence
        message = ThreadMessage.objects.create(thread=thread, sender=user, text=text, image_url=image_url)

        # 3. Broadcast
        # Group name convention: "thread_{uuid}"
        group_name = f"thread_{thread.id}"

        payload = {
            "type": "chat_message",  # Use underscore convention for handler methods
            "message": {
                "id": str(message.id),
                "thread_id": str(thread.id),
                "sender_id": str(user.id),
                "sender_username": user.username,
                "text": message.text,
                "image_url": message.image_url,
                "created_at": message.created_at.isoformat(),
            },
        }

        async_to_sync(self.channel_layer.group_send)(group_name, payload)

        return message

    def get_conversation_history(self, user, thread_id, page=1, page_size=20):
        """
        Retrieve paginated messages for a thread, ensuring user has access.
        """
        # Validation
        try:
            thread = Thread.objects.get(id=thread_id)
        except Thread.DoesNotExist:
            raise ObjectDoesNotExist("Thread not found")

        if not ThreadParticipant.objects.filter(thread=thread, user=user).exists():
            raise PermissionDenied("User is not a participant of this thread")

        # Pagination
        # Ordered by created_at DESC for history (newest first)
        messages_qs = ThreadMessage.objects.filter(thread=thread).order_by("-created_at")
        paginator = Paginator(messages_qs, page_size)

        page_obj = paginator.get_page(page)

        return page_obj

    def mark_messages_as_read(self, user, thread_id):
        """
        Mark all messages in a thread as read for the user.
        """
        try:
            thread = Thread.objects.get(id=thread_id)
        except Thread.DoesNotExist:
            raise ObjectDoesNotExist("Thread not found")

        participant = ThreadParticipant.objects.filter(thread=thread, user=user).first()
        if not participant:
            raise PermissionDenied("User is not a participant of this thread")

        from django.utils import timezone

        now = timezone.now()

        # Update participant's last_read_at
        participant.last_read_at = now
        participant.save(update_fields=["last_read_at"])

        # Update messages is_read status (messages sent by OTHERS)
        # This is efficient for visual indicators
        updated_count = (
            ThreadMessage.objects.filter(thread=thread, is_read=False).exclude(sender=user).update(is_read=True)
        )

        if updated_count > 0:
            # Broadcast read event
            group_name = f"thread_{thread.id}"
            payload = {
                "type": "chat_read",
                "message": {
                    "thread_id": str(thread.id),
                    "reader_id": str(user.id),
                    "read_at": now.isoformat(),
                },
            }
            async_to_sync(self.channel_layer.group_send)(group_name, payload)

        return updated_count
