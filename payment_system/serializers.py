from rest_framework import serializers
from .models import PaymentTracker, WebhookEvent
from django.contrib.auth import get_user_model

User = get_user_model()


class PaymentTrackerSerializer(serializers.ModelSerializer):
    user_username = serializers.CharField(source='user.username', read_only=True)
    order_id = serializers.CharField(source='order.id', read_only=True)
    
    class Meta:
        model = PaymentTracker
        fields = [
            'id', 'stripe_payment_intent_id', 'stripe_refund_id',
            'order_id', 'user_username', 'transaction_type', 'status',
            'amount', 'currency', 'notes', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class WebhookEventSerializer(serializers.ModelSerializer):
    payment_tracker_id = serializers.CharField(source='payment_tracker.id', read_only=True)
    
    class Meta:
        model = WebhookEvent
        fields = [
            'id', 'stripe_event_id', 'event_type', 'status',
            'processing_attempts', 'last_processing_error',
            'payment_tracker_id', 'created_at', 'processed_at'
        ]
        read_only_fields = ['id', 'created_at']


# Serializers for API requests
class PaymentIntentCreateSerializer(serializers.Serializer):
    """Serializer for creating payment intents"""
    order_id = serializers.UUIDField()
    payment_method_id = serializers.CharField(max_length=255, required=False)
    save_payment_method = serializers.BooleanField(default=False)


class PaymentStatusSerializer(serializers.Serializer):
    """Serializer for payment status responses"""
    payment_tracker_id = serializers.UUIDField()
    status = serializers.CharField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    currency = serializers.CharField()
    transaction_type = serializers.CharField()
    stripe_payment_intent_id = serializers.CharField(allow_blank=True)
    stripe_refund_id = serializers.CharField(allow_blank=True)


class RefundRequestSerializer(serializers.Serializer):
    """Serializer for creating refund requests"""
    order_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    reason = serializers.CharField(max_length=100)
    notes = serializers.CharField(max_length=1000, required=False)