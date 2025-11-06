import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

logger = logging.getLogger(__name__)
User = get_user_model()


class UserConsumer(AsyncWebsocketConsumer):
    """
    Simplified WebSocket consumer for basic chat connectivity.
    No database operations - WebSocket only.
    """

    async def connect(self):
        """Handle WebSocket connection"""
        # Authenticate user from query parameters
        self.user = await self.get_user_from_token()

        if self.user is None or isinstance(self.user, AnonymousUser):
            logger.warning("Unauthenticated WebSocket connection attempt")
            await self.close(code=4001)  # Unauthorized
            return

        # Create user-specific group
        self.user_group_name = f"user_{self.user.id}"

        # Join user group
        await self.channel_layer.group_add(self.user_group_name, self.channel_name)

        await self.accept()
        logger.info(f"User {self.user.username} connected to chat WebSocket")

        # Notify about successful connection
        await self.send(
            text_data=json.dumps(
                {"type": "connection_success", "user_id": self.user.id, "message": "Connected to chat WebSocket"}
            )
        )

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        if hasattr(self, "user") and self.user:
            logger.info(f"User {self.user.username} disconnected from chat WebSocket")

            # Leave user group
            if hasattr(self, "user_group_name"):
                await self.channel_layer.group_discard(self.user_group_name, self.channel_name)

    async def receive(self, text_data):
        """Handle incoming WebSocket messages"""
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get("type")

            if message_type == "ping":
                await self.handle_ping(text_data_json)
            elif message_type == "test_message":
                await self.handle_test_message(text_data_json)
            else:
                logger.warning(f"Unknown message type: {message_type}")

        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received: {text_data}")
        except Exception as e:
            logger.error(f"Error processing WebSocket message: {str(e)}")

    async def handle_ping(self, data):
        """Handle ping messages"""
        await self.send(text_data=json.dumps({"type": "pong", "message": "WebSocket connection active"}))

    async def handle_test_message(self, data):
        """Handle test messages"""
        message_content = data.get("message", "Test message")

        await self.send(
            text_data=json.dumps(
                {"type": "test_response", "message": f"Echo: {message_content}", "user_id": self.user.id}
            )
        )

    @database_sync_to_async
    def get_user_from_token(self):
        """Extract user from JWT token in query parameters"""
        try:
            # Get token from query parameters
            token = None
            query_string = self.scope.get("query_string", b"").decode()

            if query_string:
                params = dict(param.split("=") for param in query_string.split("&") if "=" in param)
                token = params.get("token")

            if not token:
                return None

            # Validate JWT token and get user
            try:
                jwt_auth = JWTAuthentication()
                validated_token = jwt_auth.get_validated_token(token)
                user = jwt_auth.get_user(validated_token)
                return user
            except (InvalidToken, TokenError):
                return None

        except Exception as e:
            logger.error(f"Error extracting user from token: {str(e)}")
            return None

    async def send_error(self, error_message):
        """Send error message to WebSocket"""
        await self.send(text_data=json.dumps({"type": "error", "message": error_message}))

    # Group message handlers
    async def new_message(self, event):
        """Send new message to WebSocket"""
        await self.send(text_data=json.dumps({"type": "new_message", "message_data": event["message_data"]}))

    async def new_chat(self, event):
        """Send new chat notification to WebSocket"""
        await self.send(text_data=json.dumps({"type": "new_chat", "chat_data": event["chat_data"]}))

    async def message_read(self, event):
        """Send message read notification to WebSocket"""
        await self.send(text_data=json.dumps({"type": "message_read", "chat_id": event["chat_id"]}))

    @classmethod
    async def notify_new_message(cls, user_id: int, message_data: dict):
        """Send new message notification to specific user"""
        print("notify_new_message", user_id, message_data)
        from channels.layers import get_channel_layer

        channel_layer = get_channel_layer()

        await channel_layer.group_send(f"user_{user_id}", {"type": "new_message", "message_data": message_data})

    @classmethod
    async def notify_new_chat(cls, user_id: int, chat_data: dict):
        """Send new chat notification to specific user"""
        from channels.layers import get_channel_layer

        channel_layer = get_channel_layer()

        await channel_layer.group_send(f"user_{user_id}", {"type": "new_chat", "chat_data": chat_data})

    @classmethod
    async def notify_message_read(cls, user_id: int, chat_id: int):
        """Send message read notification to specific user"""
        from channels.layers import get_channel_layer

        channel_layer = get_channel_layer()

        await channel_layer.group_send(f"user_{user_id}", {"type": "message_read", "chat_id": chat_id})
