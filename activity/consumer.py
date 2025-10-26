import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.contrib.auth import get_user_model
from .models import UserClick

logger = logging.getLogger(__name__)
User = get_user_model()

class ActivityConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for user activity notifications.
    Handles cart events, product updates, and general activity notifications.
    """
    
    async def connect(self):
        """Handle WebSocket connection"""
        # Authenticate user from query parameters
        self.user = await self.get_user_from_token()
        
        if self.user is None or isinstance(self.user, AnonymousUser):
            logger.warning(f"Unauthenticated WebSocket connection attempt to activity")
            await self.close(code=4001)  # Unauthorized
            return
        
        # Create user-specific activity group
        self.user_group_name = f'activity_user_{self.user.id}'
        
        # Join user activity group
        await self.channel_layer.group_add(
            self.user_group_name,
            self.channel_name
        )
        
        await self.accept()
        logger.info(f"  User {self.user.username} connected to activity WebSocket")
        
        # Send connection success with current cart count and unread messages
        cart_count = await self.get_user_cart_count()
        unread_messages = await self.get_user_unread_messages()
        await self.send(text_data=json.dumps({
            'type': 'connection_success',
            'user_id': self.user.id,
            'cart_count': cart_count,
            'unread_messages_count': unread_messages,
            'message': 'Connected to activity notifications'
        }))

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        if hasattr(self, 'user') and self.user:
            logger.info(f"User {self.user.username} disconnected from activity WebSocket")
            
            # Leave user activity group
            if hasattr(self, 'user_group_name'):
                await self.channel_layer.group_discard(
                    self.user_group_name,
                    self.channel_name
                )

    async def receive(self, text_data):
        """Handle incoming WebSocket messages"""
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type')
            
            if message_type == 'get_cart_count':
                await self.handle_get_cart_count()
            elif message_type == 'get_unread_count':
                await self.handle_get_unread_count()
            elif message_type == 'track_activity':
                await self.handle_track_activity(text_data_json)
            else:
                logger.warning(f"Unknown activity message type: {message_type}")
                
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received: {text_data}")
        except Exception as e:
            logger.error(f"Error processing activity WebSocket message: {str(e)}")

    async def handle_get_cart_count(self):
        """Handle request for current cart count"""
        cart_count = await self.get_user_cart_count()
        await self.send(text_data=json.dumps({
            'type': 'cart_count_update',
            'cart_count': cart_count
        }))

    async def handle_get_unread_count(self):
        """Handle request for current unread messages count"""
        unread_count = await self.get_user_unread_messages()
        await self.send(text_data=json.dumps({
            'type': 'unread_messages_count_update',
            'unread_messages_count': unread_count
        }))

    async def handle_track_activity(self, data):
        """Handle activity tracking requests"""
        product_id = data.get('product_id')
        action = data.get('action')
        
        if not product_id or not action:
            await self.send_error('product_id and action are required')
            return
            
        # Track the activity
        await self.track_user_activity(product_id, action)

    # Group message handlers
    async def cart_updated(self, event):
        """Send cart update notification to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'cart_updated',
            'action': event['action'],
            'product_id': event.get('product_id'),
            'cart_count': event['cart_count'],
            'message': event.get('message', 'Cart updated'),
            'quantity_change': event.get('quantity_change')
        }))

    async def activity_notification(self, event):
        """Send general activity notification to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'activity_notification',
            'notification_type': event['notification_type'],
            'title': event['title'],
            'message': event['message'],
            'data': event.get('data', {})
        }))

    async def unread_messages_count_update(self, event):
        """Send unread messages count update to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'unread_messages_count_update',
            'unread_messages_count': event['unread_count']
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
    def get_user_cart_count(self):
        """Get current user's cart count from activity tracking"""
        try:
            from marketplace.models import Cart, CartItem
            # Get user's cart first, then get cart items
            user_cart = Cart.objects.filter(user=self.user).first()
            if not user_cart:
                return 0
            
            cart_items = CartItem.objects.filter(cart=user_cart)
            return sum(item.quantity for item in cart_items)
        except Exception as e:
            logger.error(f"Error getting cart count: {str(e)}")
            return 0

    @database_sync_to_async
    def get_user_unread_messages(self):
        """Get current user's unread messages count"""
        try:
            from chat.utils import UnreadMessageTracker
            # Use sync method since we're already in database_sync_to_async
            from django.db import models
            from chat.models import Chat, Message
            
            # Get all chats where user is participant
            user_chats = Chat.objects.filter(
                models.Q(user1=self.user) | models.Q(user2=self.user)
            ).values_list('id', flat=True)
            
            # Count unread messages in all user's chats (excluding own messages)
            unread_count = Message.objects.filter(
                chat_id__in=user_chats,
                is_read=False
            ).exclude(
                sender=self.user  # Exclude own messages
            ).count()
            
            return unread_count
            
        except Exception as e:
            logger.error(f"Error getting unread messages count: {str(e)}")
            return 0

    @database_sync_to_async
    def track_user_activity(self, product_id, action):
        """Track user activity"""
        try:
            from marketplace.models import Product
            product = Product.objects.get(id=product_id)
            UserClick.track_activity(
                product=product,
                action=action,
                user=self.user
            )
            return True
        except Exception as e:
            logger.error(f"Error tracking activity: {str(e)}")
            return False

    @staticmethod
    async def notify_cart_update(user_id, action, product_id=None, cart_count=None, message=None, quantity_change=None):
        """Static method to notify user about cart updates from outside the consumer"""
        from channels.layers import get_channel_layer
        
        try:
            channel_layer = get_channel_layer()
            user_group_name = f'activity_user_{user_id}'
            
            logger.info(f"Notifying user {user_id} about cart update: {action}")
            
            # Ensure payload is JSON-serializable for channel layer
            safe_product_id = str(product_id) if product_id is not None else None
            safe_cart_count = int(cart_count) if cart_count is not None else None
            safe_message = str(message) if message is not None else None
            safe_quantity_change = int(quantity_change) if quantity_change is not None else None

            await channel_layer.group_send(
                user_group_name,
                {
                    'type': 'cart_updated',
                    'action': action,
                    'product_id': safe_product_id,
                    'cart_count': safe_cart_count,
                    'message': safe_message,
                    'quantity_change': safe_quantity_change
                }
            )
            
            logger.info(f"Cart update notification sent to user {user_id}")
            
        except Exception as e:
            logger.error(f"Failed to send cart update notification to user {user_id}: {str(e)}")

    @staticmethod
    async def notify_activity(user_id, notification_type, title, message, data=None):
        """Static method to send activity notifications from outside the consumer"""
        from channels.layers import get_channel_layer
        
        try:
            channel_layer = get_channel_layer()
            user_group_name = f'activity_user_{user_id}'
            
            logger.info(f"Sending activity notification to user {user_id}: {notification_type}")
            
            await channel_layer.group_send(
                user_group_name,
                {
                    'type': 'activity_notification',
                    'notification_type': notification_type,
                    'title': title,
                    'message': message,
                    'data': data or {}
                }
            )
            
            logger.info(f"Activity notification sent to user {user_id}")
            
        except Exception as e:
            logger.error(f"Failed to send activity notification to user {user_id}: {str(e)}")

    @staticmethod
    async def notify_unread_count_update(user_id, unread_count):
        """Static method to notify user about unread messages count update"""
        from channels.layers import get_channel_layer
        
        try:
            channel_layer = get_channel_layer()
            user_group_name = f'activity_user_{user_id}'
            
            logger.info(f"Notifying user {user_id} about unread count: {unread_count}")
            
            await channel_layer.group_send(
                user_group_name,
                {
                    'type': 'unread_messages_count_update',
                    'unread_count': unread_count
                }
            )
            
            logger.info(f"Unread count notification sent to user {user_id}")
            
        except Exception as e:
            logger.error(f"Failed to send unread count notification to user {user_id}: {str(e)}")
