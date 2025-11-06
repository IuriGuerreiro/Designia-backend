from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Chat, Message

User = get_user_model()


class ChatUserSerializer(serializers.ModelSerializer):
    """Serializer for user info in chat context"""

    profile_picture_temp_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "username", "email", "first_name", "last_name", "profile_picture_temp_url")
        read_only_fields = ("id", "email")

    def get_profile_picture_temp_url(self, obj):
        """Get user's profile picture temporary URL"""
        try:
            if hasattr(obj, "profile") and obj.profile:
                return obj.profile.get_profile_picture_temp_url()
        except Exception:
            pass
        return None


class MessageSerializer(serializers.ModelSerializer):
    """Serializer for chat messages"""

    sender = ChatUserSerializer(read_only=True)
    image_temp_url = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = (
            "id",
            "chat",
            "sender",
            "message_type",
            "text_content",
            "image_url",
            "image_temp_url",
            "created_at",
            "is_read",
            "read_at",
        )
        read_only_fields = ("id", "sender", "created_at", "is_read", "read_at", "image_temp_url")

    def get_image_temp_url(self, obj):
        """Get temporary URL for message image"""
        return obj.get_image_temp_url()

    def validate(self, attrs):
        """Validate message data"""
        message_type = attrs.get("message_type", "text")
        text_content = attrs.get("text_content")
        image_url = attrs.get("image_url")

        if message_type == "text" and not text_content:
            raise serializers.ValidationError("Text messages must have text content")
        if message_type == "image" and not image_url:
            raise serializers.ValidationError("Image messages must have image URL")

        return attrs


class MessageCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating messages"""

    class Meta:
        model = Message
        fields = ("message_type", "text_content", "image_url")

    def validate(self, attrs):
        """Validate message creation data"""
        message_type = attrs.get("message_type", "text")
        text_content = attrs.get("text_content")
        image_url = attrs.get("image_url")

        if message_type == "text":
            if not text_content or not text_content.strip():
                raise serializers.ValidationError("Text messages must have non-empty text content")
        elif message_type == "image":
            if not image_url:
                raise serializers.ValidationError("Image messages must have image URL")
        else:
            raise serializers.ValidationError("Invalid message type")

        return attrs


class ChatSerializer(serializers.ModelSerializer):
    """Serializer for chat conversations"""

    user1 = ChatUserSerializer(read_only=True)
    user2 = ChatUserSerializer(read_only=True)
    last_message = MessageSerializer(read_only=True)
    other_user = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = Chat
        fields = ("id", "user1", "user2", "other_user", "created_at", "updated_at", "last_message", "unread_count")
        read_only_fields = ("id", "created_at", "updated_at")

    def get_other_user(self, obj):
        """Get the other user in the chat (relative to current user)"""
        request = self.context.get("request")
        if request and hasattr(request, "user"):
            other_user = obj.get_other_user(request.user)
            return ChatUserSerializer(other_user).data
        return None

    def get_unread_count(self, obj):
        """Get count of unread messages for current user"""
        request = self.context.get("request")
        if request and hasattr(request, "user"):
            # Count messages not sent by current user and not read
            return obj.messages.filter(is_read=False).exclude(sender=request.user).count()
        return 0


class ChatCreateSerializer(serializers.Serializer):
    """Serializer for creating new chats"""

    user_id = serializers.IntegerField()

    def validate_user_id(self, value):
        """Validate that user exists and is not current user"""
        try:
            user = User.objects.get(id=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("User does not exist") from None

        request = self.context.get("request")
        if request and hasattr(request, "user") and user == request.user:
            raise serializers.ValidationError("Cannot create chat with yourself")

        return value
