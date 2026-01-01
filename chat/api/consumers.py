import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from chat.domain.models import ThreadParticipant
from chat.domain.services.chat_service import ChatService


logger = logging.getLogger(__name__)


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]

        # 1. Validation: User must be authenticated
        if not self.user.is_authenticated:
            logger.warning(f"Unauthenticated connection attempt to {self.channel_name}")
            await self.close(code=4001)  # Unauthorized
            return

        # 2. Extract Thread ID
        self.thread_id = self.scope["url_route"]["kwargs"].get("thread_id")
        self.group_name = f"thread_{self.thread_id}"

        # 3. Check Permissions (Async DB Call)
        has_permission = await self.check_thread_permission(self.user, self.thread_id)
        if not has_permission:
            logger.warning(f"User {self.user.id} denied access to thread {self.thread_id}")
            await self.close(code=4003)  # Forbidden
            return

        # 4. Join Group
        await self.channel_layer.group_add(self.group_name, self.channel_name)

        await self.accept()
        logger.info(f"User {self.user.id} connected to thread {self.thread_id}")

    async def disconnect(self, close_code):
        # Leave group
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            msg_type = data.get("type")

            if msg_type == "chat.message":
                payload = data.get("payload", {})
                text = payload.get("text")
                image_url = payload.get("image_url")  # Optional

                if not text and not image_url:
                    await self.send_error("Message must have text or image.")
                    return

                # Persist and Broadcast via Service
                try:
                    await self.save_and_broadcast_message(text, image_url)
                except Exception as e:
                    logger.error(f"Error saving message: {e}")
                    await self.send_error("Failed to send message")

            elif msg_type == "ping":
                await self.send(text_data=json.dumps({"type": "pong"}))
            else:
                await self.send_error("Unknown message type")

        except json.JSONDecodeError:
            await self.send_error("Invalid JSON")
        except Exception as e:
            logger.error(f"Error in receive: {e}")
            await self.send_error("Internal server error")

    async def chat_message(self, event):
        """
        Handler for 'chat.message' events sent from the Channel Layer.
        """
        # Send message to WebSocket
        await self.send(text_data=json.dumps({"type": "chat.message", "data": event["message"]}))

    async def send_error(self, message, code="error"):
        await self.send(text_data=json.dumps({"type": "error", "code": code, "message": message}))

    @database_sync_to_async
    def check_thread_permission(self, user, thread_id):
        try:
            # We use string id for UUID comparison usually, but UUIDField handles it
            return ThreadParticipant.objects.filter(thread__id=thread_id, user=user).exists()
        except Exception:
            return False

    @database_sync_to_async
    def save_and_broadcast_message(self, text, image_url):
        service = ChatService()
        # This persists AND sends to group (so self.chat_message will be triggered)
        service.send_message(self.user, self.thread_id, text, image_url)
