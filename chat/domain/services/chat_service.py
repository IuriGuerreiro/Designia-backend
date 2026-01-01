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
