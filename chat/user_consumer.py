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

class UserConsumer(AsyncWebsocketConsumer):
    """
    Global WebSocket consumer for user-level real-time notifications.
    Handles messages from all chats the user participates in.
    """
    
    async def connect(self):
        """Handle WebSocket connection"""
        # Authenticate user from query parameters
        self.user = await self.get_user_from_token()
        
        if self.user is None or isinstance(self.user, AnonymousUser):
            logger.warning(f"Unauthenticated WebSocket connection attempt")
            await self.close(code=4001)  # Unauthorized
            return
        
        # Create user-specific group
        self.user_group_name = f'user_{self.user.id}'
        
        # Join user group
        await self.channel_layer.group_add(
            self.user_group_name,
            self.channel_name
        )
        
        # Also join all chat groups the user is part of
        await self.join_user_chat_groups()
        
        await self.accept()
        logger.info(f"✅ User {self.user.username} connected to global WebSocket")
        
        # Notify about successful connection
        await self.send(text_data=json.dumps({
            'type': 'connection_success',
            'user_id': self.user.id,
            'message': 'Connected to global notifications'
        }))

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        if hasattr(self, 'user') and self.user:
            logger.info(f"❌ User {self.user.username} disconnected from global WebSocket")
            
            # Leave user group
            if hasattr(self, 'user_group_name'):
                await self.channel_layer.group_discard(
                    self.user_group_name,
                    self.channel_name
                )
            
            # Leave all chat groups
            await self.leave_user_chat_groups()

    async def receive(self, text_data):
        """Handle incoming WebSocket messages"""
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type')
            
            if message_type == 'chat_message':
                await self.handle_chat_message(text_data_json)
            elif message_type == 'typing_start':
                await self.handle_typing_start(text_data_json)
            elif message_type == 'typing_stop':
                await self.handle_typing_stop(text_data_json)
            elif message_type == 'mark_read':
                await self.handle_mark_read(text_data_json)
            elif message_type == 'join_chat':
                await self.handle_join_chat(text_data_json)
            elif message_type == 'leave_chat':
                await self.handle_leave_chat(text_data_json)
            else:
                logger.warning(f"Unknown message type: {message_type}")
                
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received: {text_data}")
        except Exception as e:
            logger.error(f"Error processing WebSocket message: {str(e)}")

    async def handle_chat_message(self, data):
        """Handle sending chat message to specific chat"""
        chat_id = data.get('chat_id')
        message_text = data.get('text_content', '').strip()
        image_url = data.get('image_url')
        msg_type = data.get('message_type', 'text')
        
        if not chat_id:
            await self.send_error('chat_id is required')
            return
        
        # Validate message
        if msg_type == 'text' and not message_text:
            await self.send_error('Text message cannot be empty')
            return
            
        # Verify user has access to this chat
        has_access = await self.verify_chat_access(chat_id)
        if not has_access:
            await self.send_error('Access denied to this chat')
            return
        
        # Create message in database
        message = await self.create_message(chat_id, message_text, image_url, msg_type)
        
        # Serialize message
        message_data = await self.serialize_message(message)
        
        # Broadcast to chat group
        chat_group_name = f'chat_{chat_id}'
        await self.channel_layer.group_send(
            chat_group_name,
            {
                'type': 'chat_message',
                'message': message_data,
                'chat_id': chat_id
            }
        )
        
        logger.info(f"Message {message.id} sent by user {self.user.id} in chat {chat_id}")

    async def handle_typing_start(self, data):
        """Handle typing start notification for specific chat"""
        chat_id = data.get('chat_id')
        if not chat_id:
            await self.send_error('chat_id is required for typing')
            return
            
        has_access = await self.verify_chat_access(chat_id)
        if not has_access:
            return
            
        logger.info(f"🔤 User {self.user.username} started typing in chat {chat_id}")
        
        chat_group_name = f'chat_{chat_id}'
        await self.channel_layer.group_send(
            chat_group_name,
            {
                'type': 'typing_start',
                'user_id': self.user.id,
                'username': self.user.username,
                'chat_id': chat_id
            }
        )

    async def handle_typing_stop(self, data):
        """Handle typing stop notification for specific chat"""
        chat_id = data.get('chat_id')
        if not chat_id:
            return
            
        has_access = await self.verify_chat_access(chat_id)
        if not has_access:
            return
            
        logger.info(f"⏹️ User {self.user.username} stopped typing in chat {chat_id}")
        
        chat_group_name = f'chat_{chat_id}'
        await self.channel_layer.group_send(
            chat_group_name,
            {
                'type': 'typing_stop',
                'user_id': self.user.id,
                'username': self.user.username,
                'chat_id': chat_id
            }
        )

    async def handle_mark_read(self, data):
        """Handle mark messages as read for specific chat"""
        chat_id = data.get('chat_id')
        if not chat_id:
            return
            
        has_access = await self.verify_chat_access(chat_id)
        if not has_access:
            return
            
        await self.mark_messages_read(chat_id)
        
        chat_group_name = f'chat_{chat_id}'
        await self.channel_layer.group_send(
            chat_group_name,
            {
                'type': 'messages_read',
                'user_id': self.user.id,
                'chat_id': chat_id
            }
        )

    async def handle_join_chat(self, data):
        """Handle joining a specific chat group"""
        chat_id = data.get('chat_id')
        if not chat_id:
            return
            
        has_access = await self.verify_chat_access(chat_id)
        if not has_access:
            await self.send_error('Access denied to this chat')
            return
            
        chat_group_name = f'chat_{chat_id}'
        await self.channel_layer.group_add(chat_group_name, self.channel_name)
        logger.info(f"User {self.user.username} joined chat group {chat_id}")

    async def handle_leave_chat(self, data):
        """Handle leaving a specific chat group"""
        chat_id = data.get('chat_id')
        if not chat_id:
            return
            
        chat_group_name = f'chat_{chat_id}'
        await self.channel_layer.group_discard(chat_group_name, self.channel_name)
        logger.info(f"User {self.user.username} left chat group {chat_id}")

    # Group message handlers
    async def chat_message(self, event):
        """Send chat message to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message': event['message'],
            'chat_id': event['chat_id']
        }))

    async def typing_start(self, event):
        """Send typing start notification to WebSocket"""
        # Don't send to the user who is typing
        if event['user_id'] != self.user.id:
            logger.info(f"📤 Sending typing_start to user {self.user.username}: {event['username']} is typing in chat {event['chat_id']}")
            await self.send(text_data=json.dumps({
                'type': 'typing_start',
                'user_id': event['user_id'],
                'username': event['username'],
                'chat_id': event['chat_id']
            }))

    async def typing_stop(self, event):
        """Send typing stop notification to WebSocket"""
        # Don't send to the user who stopped typing
        if event['user_id'] != self.user.id:
            logger.info(f"📤 Sending typing_stop to user {self.user.username}: {event['username']} stopped typing in chat {event['chat_id']}")
            await self.send(text_data=json.dumps({
                'type': 'typing_stop',
                'user_id': event['user_id'],
                'username': event['username'],
                'chat_id': event['chat_id']
            }))

    async def messages_read(self, event):
        """Send messages read notification to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'messages_read',
            'user_id': event['user_id'],
            'chat_id': event['chat_id']
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
    def verify_chat_access(self, chat_id):
        """Verify user has access to the specified chat"""
        try:
            chat = Chat.objects.get(id=chat_id)
            return chat.user1 == self.user or chat.user2 == self.user
        except Chat.DoesNotExist:
            return False

    @database_sync_to_async 
    def create_message(self, chat_id, text_content, image_url, message_type):
        """Create message in database"""
        chat = Chat.objects.get(id=chat_id)
        message = Message.objects.create(
            chat=chat,
            sender=self.user,
            text_content=text_content if message_type == 'text' else '',
            image_url=image_url if message_type == 'image' else None,
            message_type=message_type
        )
        
        # Update chat's last activity
        chat.save()  # This updates updated_at automatically
        
        return message

    @database_sync_to_async
    def serialize_message(self, message):
        """Serialize message to JSON"""
        serializer = MessageSerializer(message)
        return serializer.data

    @database_sync_to_async
    def mark_messages_read(self, chat_id):
        """Mark all messages in chat as read for the current user"""
        try:
            chat = Chat.objects.get(id=chat_id)
            unread_messages = Message.objects.filter(
                chat=chat,
                is_read=False
            ).exclude(sender=self.user)
            
            unread_messages.update(is_read=True)
            logger.info(f"Marked {unread_messages.count()} messages as read in chat {chat_id}")
            
        except Exception as e:
            logger.error(f"Error marking messages as read: {str(e)}")

    @database_sync_to_async
    def get_user_chats(self):
        """Get all chats the user participates in"""
        from django.db.models import Q
        return list(Chat.objects.filter(Q(user1=self.user) | Q(user2=self.user)).values_list('id', flat=True))

    async def join_user_chat_groups(self):
        """Join all chat groups the user participates in"""
        chat_ids = await self.get_user_chats()
        for chat_id in chat_ids:
            chat_group_name = f'chat_{chat_id}'
            await self.channel_layer.group_add(chat_group_name, self.channel_name)
        logger.info(f"User {self.user.username} joined {len(chat_ids)} chat groups")

    async def leave_user_chat_groups(self):
        """Leave all chat groups the user participates in"""
        chat_ids = await self.get_user_chats()
        for chat_id in chat_ids:
            chat_group_name = f'chat_{chat_id}'
            await self.channel_layer.group_discard(chat_group_name, self.channel_name)
        logger.info(f"User {self.user.username} left {len(chat_ids)} chat groups")

    async def send_error(self, error_message):
        """Send error message to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': error_message
        }))