from django.contrib.auth import get_user_model
from rest_framework import serializers

from chat.domain.models import Thread, ThreadMessage, ThreadParticipant
from marketplace.catalog.domain.models.catalog import Product


User = get_user_model()


class ThreadParticipantSerializer(serializers.ModelSerializer):
    username = serializers.ReadOnlyField(source="user.username")
    avatar = serializers.SerializerMethodField()

    class Meta:
        model = ThreadParticipant
        fields = ("id", "user", "username", "avatar", "joined_at", "last_read_at")

    def get_avatar(self, obj):
        try:
            return obj.user.profile.get_profile_picture_temp_url()
        except Exception:
            return None


class ThreadMessageSerializer(serializers.ModelSerializer):
    sender_username = serializers.ReadOnlyField(source="sender.username")

    class Meta:
        model = ThreadMessage
        fields = ("id", "sender", "sender_username", "message_type", "text", "image_url", "created_at", "is_read")


class ThreadSerializer(serializers.ModelSerializer):
    participants = ThreadParticipantSerializer(source="thread_participants", many=True, read_only=True)
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = Thread
        fields = ("id", "created_at", "updated_at", "is_group", "name", "participants", "last_message", "unread_count")
        read_only_fields = ("id", "created_at", "updated_at")

    def get_last_message(self, obj):
        last_msg = obj.messages.order_by("-created_at").first()
        if last_msg:
            return ThreadMessageSerializer(last_msg).data
        return None

    def get_unread_count(self, obj):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            # Simple unread count: messages where sender is NOT current user and is_read is False
            # Note: Legacy Message model used is_read, ThreadMessage also has it.
            return obj.messages.exclude(sender=request.user).filter(is_read=False).count()
        return 0


class StartConversationSerializer(serializers.Serializer):
    product_id = serializers.UUIDField(required=True)

    def validate_product_id(self, value):
        try:
            product = Product.objects.get(id=value)
            return product
        except Product.DoesNotExist:
            raise serializers.ValidationError("Product not found")
