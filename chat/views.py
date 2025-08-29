from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.conf import settings
from django.utils import timezone
from asgiref.sync import async_to_sync

from .models import Chat, Message
from .serializers import (
    ChatSerializer, ChatCreateSerializer, MessageSerializer, 
    MessageCreateSerializer
)
from .user_consumer import UserConsumer

User = get_user_model()


class MessagePagination(PageNumberPagination):
    """Custom pagination for messages"""
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 100


class ChatListView(generics.ListCreateAPIView):
    """
    List user's chats or create a new chat
    """
    serializer_class = ChatSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Get chats for current user"""
        user = self.request.user
        return Chat.objects.filter(
            Q(user1=user) | Q(user2=user)
        ).select_related('user1', 'user2', 'last_message__sender')
    
    def create(self, request, *args, **kwargs):
        """Create a new chat with another user"""
        serializer = ChatCreateSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            other_user_id = serializer.validated_data['user_id']
            other_user = get_object_or_404(User, id=other_user_id)
            
            # Get or create chat
            chat, created = Chat.get_or_create_chat(request.user, other_user)
            
            # Serialize chat for response and WebSocket notification
            chat_serializer = ChatSerializer(chat, context={'request': request})
            chat_data = chat_serializer.data
            
            # If chat was newly created, notify the other user via WebSocket
            if created:
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"📬 New chat created between {request.user.username} and {other_user.username} (chat_id: {chat.id})")
                
                try:
                    # Create a context for the other user to get the correct "other_user" field
                    other_user_request = type('Request', (), {'user': other_user})()
                    other_user_serializer = ChatSerializer(chat, context={'request': other_user_request})
                    other_user_chat_data = other_user_serializer.data
                    
                    logger.info(f"📤 Attempting to notify user {other_user.username} (id: {other_user.id}) about new chat")
                    
                    # Notify the other user about the new chat
                    async_to_sync(UserConsumer.notify_new_chat)(
                        user_id=other_user.id,
                        chat_data=other_user_chat_data
                    )
                    
                    logger.info(f"  Successfully initiated WebSocket notification for new chat {chat.id}")
                    
                except Exception as e:
                    # Log the error but don't fail the chat creation
                    logger.error(f" Failed to notify user {other_user.id} about new chat: {str(e)}")
            else:
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"🔄 Existing chat returned between {request.user.username} and {other_user.username} (chat_id: {chat.id})")
            
            return Response(chat_data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ChatDetailView(generics.RetrieveAPIView):
    """
    Get details of a specific chat
    """
    serializer_class = ChatSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Only return chats the user is part of"""
        user = self.request.user
        return Chat.objects.filter(
            Q(user1=user) | Q(user2=user)
        ).select_related('user1', 'user2', 'last_message__sender')


class MessageListView(generics.ListCreateAPIView):
    """
    List messages in a chat or send a new message
    """
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = MessagePagination
    
    
    def get_queryset(self):
        """Get messages for the specified chat"""
        chat_id = self.kwargs['chat_id']
        chat = get_object_or_404(Chat, id=chat_id)
        
        # Verify user is part of the chat
        if not chat.has_user(self.request.user):
            return Message.objects.none()
        
        return Message.objects.filter(chat=chat).select_related('sender', 'sender__profile').order_by('-created_at')
    
    def create(self, request, *args, **kwargs):
        """Send a new message in the chat"""
        chat_id = self.kwargs['chat_id']
        chat = get_object_or_404(Chat, id=chat_id)
        
        # Verify user is part of the chat
        if not chat.has_user(request.user):
            return Response(
                {'error': 'You are not part of this chat'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Use create serializer for validation
        create_serializer = MessageCreateSerializer(data=request.data)
        if create_serializer.is_valid():
            # Create message
            message = Message.objects.create(
                chat=chat,
                sender=request.user,
                **create_serializer.validated_data
            )
            
            # Return serialized message
            response_serializer = MessageSerializer(message)
            message_data = response_serializer.data
            
            # Send WebSocket notification to the other user
            other_user = chat.get_other_user(request.user)
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"📤 New message in chat {chat.id}: {message.text_content[:50]}... -> notifying user {other_user.id}")
            
            try:
                # Notify the other user about the new message
                async_to_sync(UserConsumer.notify_new_message)(
                    user_id=other_user.id,
                    message_data=message_data
                )
                logger.info(f"✅ Successfully notified user {other_user.id} about new message")
                
            except Exception as e:
                # Log the error but don't fail the message creation
                logger.error(f"❌ Failed to notify user {other_user.id} about new message: {str(e)}")
            
            return Response(message_data, status=status.HTTP_201_CREATED)
        
        return Response(create_serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def upload_chat_image(request):
    """Upload image for chat messages to S3"""
    try:
        if not getattr(settings, 'USE_S3', False):
            return Response({
                'error': 'S3 storage is not enabled'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        from utils.s3_storage import get_s3_storage, S3StorageError
        
        # Get image file from request
        image_file = request.FILES.get('image')
        if not image_file:
            return Response({
                'error': 'Image file is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate image file size
        max_size = 10 * 1024 * 1024  # 10MB
        if image_file.size > max_size:
            return Response({
                'error': f'Image file too large. Maximum size is {max_size // (1024*1024)}MB'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check file type
        allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp']
        if hasattr(image_file, 'content_type') and image_file.content_type not in allowed_types:
            return Response({
                'error': f'Invalid file type. Allowed types: {", ".join(allowed_types)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            s3_storage = get_s3_storage()
            
            # Generate S3 key for chat image
            import os
            from django.utils import timezone
            timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
            file_extension = os.path.splitext(image_file.name)[1].lower()
            key = f"chat/images/{request.user.id}/{timestamp}{file_extension}"
            
            # Upload to S3
            result = s3_storage.upload_file(
                file_obj=image_file,
                key=key,
                metadata={
                    'user_id': str(request.user.id),
                    'file_type': 'chat_image',
                    'uploaded_at': timezone.now().isoformat()
                },
                public=False  # Chat images are private
            )
            
            # Generate temporary URL for immediate use
            temp_url = s3_storage.get_file_url(key, expires_in=3600)
            
            return Response({
                'message': 'Image uploaded successfully',
                'image_url': result['key'],
                'image_temp_url': temp_url,
                'size': result['size'],
                'content_type': result['content_type'],
                'uploaded_at': result['uploaded_at']
            }, status=status.HTTP_200_OK)
            
        except S3StorageError as e:
            return Response({
                'error': f'Failed to upload image: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
    except Exception as e:
        return Response({
            'error': 'Service may be unavailable. Please try again later.'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def mark_messages_read(request, chat_id):
    """Mark all messages in a chat as read for the current user"""
    try:
        chat = get_object_or_404(Chat, id=chat_id)
        
        # Verify user is part of the chat
        if not chat.has_user(request.user):
            return Response(
                {'error': 'You are not part of this chat'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Mark unread messages as read (excluding messages sent by current user)
        updated_count = Message.objects.filter(
            chat=chat,
            is_read=False
        ).exclude(sender=request.user).update(
            is_read=True,
            read_at=timezone.now()
        )
        
        # Send WebSocket notification to the other user that messages were read
        if updated_count > 0:
            other_user = chat.get_other_user(request.user)
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"📖 Messages marked as read in chat {chat.id} by user {request.user.id} -> notifying user {other_user.id}")
            
            try:
                # Notify the other user that their messages were read
                async_to_sync(UserConsumer.notify_message_read)(
                    user_id=other_user.id,
                    chat_id=chat.id
                )
                logger.info(f"✅ Successfully notified user {other_user.id} about messages read")
                
            except Exception as e:
                # Log the error but don't fail the operation
                logger.error(f"❌ Failed to notify user {other_user.id} about messages read: {str(e)}")
        
        return Response({
            'message': f'{updated_count} messages marked as read'
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': 'Service may be unavailable. Please try again later.'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def search_users(request):
    """Search for users to start a chat with"""
    try:
        query = request.GET.get('q', '').strip()
        if not query:
            return Response({
                'error': 'Search query is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Search users by username, email, first_name, last_name
        users = User.objects.filter(
            Q(username__icontains=query) |
            Q(email__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query)
        ).exclude(id=request.user.id)[:20]  # Limit to 20 results
        
        from .serializers import ChatUserSerializer
        serializer = ChatUserSerializer(users, many=True)
        
        return Response({
            'users': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': 'Service may be unavailable. Please try again later.'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)