import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.contrib.auth import get_user_model
from .models import Chat, Message
from .serializers import MessageSerializer

logger = logging.getLogger(__name__)
User = get_user_model()

class ChatConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time chat functionality.
    Handles joining/leaving chat rooms and broadcasting messages.
    """
    
    async def connect(self):
        """Handle WebSocket connection"""
        self.chat_id = self.scope['url_route']['kwargs']['chat_id']
        self.room_group_name = f'chat_{self.chat_id}'
        
        # Authenticate user from query parameters or headers
        self.user = await self.get_user_from_token()
        
        if self.user is None or isinstance(self.user, AnonymousUser):
            logger.warning(f"Unauthenticated WebSocket connection attempt for chat {self.chat_id}")
            await self.close(code=4001)  # Unauthorized
            return
        
        # Verify user has access to this chat
        has_access = await self.verify_chat_access()
        if not has_access:
            logger.warning(f"User {self.user.id} attempted to access chat {self.chat_id} without permission")
            await self.close(code=4003)  # Forbidden
            return
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        logger.info(f"User {self.user.id} connected to chat {self.chat_id}")
        
        # Notify other users that someone joined
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'user_joined',
                'user_id': self.user.id,
                'username': self.user.username,
                'chat_id': self.chat_id
            }
        )

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        if hasattr(self, 'room_group_name') and hasattr(self, 'user'):
            # Send typing_stop to ensure user is no longer shown as typing
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'typing_stop',
                    'user_id': self.user.id,
                    'username': self.user.username,
                    'chat_id': self.chat_id
                }
            )
            
            # Leave room group
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            
            # Notify other users that someone left
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'user_left',
                    'user_id': self.user.id,
                    'username': self.user.username,
                    'chat_id': self.chat_id
                }
            )
            
            logger.info(f"User {self.user.id} disconnected from chat {self.chat_id} - sent typing_stop cleanup")

    async def receive(self, text_data):
        """Handle messages from WebSocket"""
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type')
            
            if message_type == 'chat_message':
                await self.handle_chat_message(text_data_json)
            elif message_type == 'typing_start':
                await self.handle_typing_start()
            elif message_type == 'typing_stop':
                await self.handle_typing_stop()
            elif message_type == 'mark_read':
                await self.handle_mark_read()
            else:
                logger.warning(f"Unknown message type: {message_type}")
                
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received: {text_data}")
        except Exception as e:
            logger.error(f"Error processing WebSocket message: {str(e)}")

    async def handle_chat_message(self, data):
        """Handle incoming chat message"""
        message_text = data.get('text_content', '').strip()
        image_url = data.get('image_url')
        msg_type = data.get('message_type', 'text')
        
        # Validate message
        if msg_type == 'text' and not message_text:
            await self.send_error('Text message cannot be empty')
            return
        elif msg_type == 'image' and not image_url:
            await self.send_error('Image URL required for image messages')
            return
        
        # Save message to database
        message = await self.save_message(msg_type, message_text, image_url)
        if not message:
            await self.send_error('Failed to save message')
            return
        
        # Serialize message for broadcasting
        message_data = await self.serialize_message(message)
        
        # Send message to room group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': message_data,
                'chat_id': self.chat_id
            }
        )
        
        logger.info(f"Message {message.id} sent by user {self.user.id} in chat {self.chat_id}")

    async def handle_typing_start(self):
        """Handle typing start notification"""
        logger.info(f"User {self.user.username} (ID: {self.user.id}) started typing in chat {self.chat_id}")
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'typing_start',
                'user_id': self.user.id,
                'username': self.user.username,
                'chat_id': self.chat_id
            }
        )

    async def handle_typing_stop(self):
        """Handle typing stop notification"""
        logger.info(f"User {self.user.username} (ID: {self.user.id}) stopped typing in chat {self.chat_id}")
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'typing_stop',
                'user_id': self.user.id,
                'username': self.user.username,
                'chat_id': self.chat_id
            }
        )

    async def handle_mark_read(self):
        """Handle mark messages as read"""
        await self.mark_messages_read()
        
        # Notify other users about read status
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'messages_read',
                'user_id': self.user.id,
                'chat_id': self.chat_id
            }
        )

    # Message handlers for group sends
    async def chat_message(self, event):
        """Send chat message to WebSocket"""
        message = event['message']
        chat_id = event.get('chat_id', self.chat_id)
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message': message,
            'chat_id': chat_id
        }))

    async def user_joined(self, event):
        """Send user joined notification to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'user_joined',
            'user_id': event['user_id'],
            'username': event['username'],
            'chat_id': event.get('chat_id', self.chat_id)
        }))

    async def user_left(self, event):
        """Send user left notification to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'user_left',
            'user_id': event['user_id'],
            'username': event['username'],
            'chat_id': event.get('chat_id', self.chat_id)
        }))

    async def typing_start(self, event):
        """Send typing start notification to WebSocket"""
        # Don't send to the user who is typing
        if event['user_id'] != self.user.id:
            logger.info(f"Sending typing_start to user {self.user.username}")
            await self.send(text_data=json.dumps({
                'type': 'typing_start',
                'user_id': event['user_id'],
                'username': event['username'],
                'chat_id': event.get('chat_id', self.chat_id)
            }))
        else:
            logger.info(f"Not sending typing_start to self ({self.user.username})")

    async def typing_stop(self, event):
        """Send typing stop notification to WebSocket"""
        # Don't send to the user who stopped typing
        if event['user_id'] != self.user.id:
            logger.info(f"Sending typing_stop to user {self.user.username}: {event['username']} stopped typing")
            await self.send(text_data=json.dumps({
                'type': 'typing_stop',
                'user_id': event['user_id'],
                'username': event['username'],
                'chat_id': event.get('chat_id', self.chat_id)
            }))
        else:
            logger.info(f"Not sending typing_stop to self ({self.user.username})")

    async def messages_read(self, event):
        """Send messages read notification to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'messages_read',
            'user_id': event['user_id'],
            'chat_id': event['chat_id']
        }))

    async def send_error(self, error_message):
        """Send error message to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': error_message
        }))

    # Database operations
    @database_sync_to_async
    def get_user_from_token(self):
        """Extract user from JWT token in query parameters"""
        try:
            # Get token from query parameters
            token = None
            query_string = self.scope.get('query_string', b'').decode()
            
            if query_string:
                params = dict(param.split('=') for param in query_string.split('&') if '=' in param)
                token = params.get('token')
            
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

    @database_sync_to_async
    def verify_chat_access(self):
        """Verify that the user has access to this chat"""
        try:
            chat = Chat.objects.get(id=self.chat_id)
            return chat.user1 == self.user or chat.user2 == self.user
        except Chat.DoesNotExist:
            return False

    @database_sync_to_async
    def save_message(self, message_type, text_content=None, image_url=None):
        """Save message to database"""
        try:
            chat = Chat.objects.get(id=self.chat_id)
            message = Message.objects.create(
                chat=chat,
                sender=self.user,
                message_type=message_type,
                text_content=text_content,
                image_url=image_url
            )
            
            # Update chat's last message
            chat.last_message = message
            chat.save()
            
            return message
        except Exception as e:
            logger.error(f"Error saving message: {str(e)}")
            return None

    @database_sync_to_async
    def serialize_message(self, message):
        """Serialize message for JSON response"""
        serializer = MessageSerializer(message)
        return serializer.data

    @database_sync_to_async
    def mark_messages_read(self):
        """Mark all unread messages in this chat as read for the current user"""
        try:
            chat = Chat.objects.get(id=self.chat_id)
            # Mark unread messages from the other user as read
            Message.objects.filter(
                chat=chat,
                is_read=False
            ).exclude(
                sender=self.user
            ).update(is_read=True)
            
            return True
        except Exception as e:
            logger.error(f"Error marking messages as read: {str(e)}")
            return False