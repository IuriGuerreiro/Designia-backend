from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import PaymentTracker, Payout, PayoutItem

User = get_user_model()


class PaymentTrackerSerializer(serializers.ModelSerializer):
    user_username = serializers.CharField(source="user.username", read_only=True)
    order_id = serializers.CharField(source="order.id", read_only=True)

    class Meta:
        model = PaymentTracker
        fields = [
            "id",
            "stripe_payment_intent_id",
            "stripe_refund_id",
            "order_id",
            "user_username",
            "transaction_type",
            "status",
            "amount",
            "currency",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


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


# Payout-related serializers
class PayoutItemSerializer(serializers.ModelSerializer):
    """Serializer for individual payout items with order details"""

    order_id = serializers.CharField(source="order_id", read_only=True)
    order_total = serializers.CharField(source="transfer_amount", read_only=True)
    order_date = serializers.DateTimeField(source="transfer_date", read_only=True)

    class Meta:
        model = PayoutItem
        fields = [
            "id",
            "order_id",
            "item_names",
            "transfer_amount",
            "transfer_currency",
            "transfer_date",
            "order_total",
            "order_date",
        ]


class PayoutSerializer(serializers.ModelSerializer):
    """Serializer for payouts with complete details"""

    payout_items = PayoutItemSerializer(many=True, read_only=True)
    seller_username = serializers.CharField(source="seller.username", read_only=True)
    formatted_amount = serializers.CharField(source="amount_formatted", read_only=True)
    is_completed = serializers.BooleanField(read_only=True)
    is_failed = serializers.BooleanField(read_only=True)
    days_since_created = serializers.IntegerField(read_only=True)

    class Meta:
        model = Payout
        fields = [
            "id",
            "stripe_payout_id",
            "seller_username",
            "status",
            "payout_type",
            "amount_decimal",
            "formatted_amount",
            "currency",
            "transfer_count",
            "total_gross_amount",
            "total_fees",
            "bank_account_last4",
            "bank_name",
            "arrival_date",
            "failure_code",
            "failure_message",
            "description",
            "is_completed",
            "is_failed",
            "days_since_created",
            "created_at",
            "updated_at",
            "payout_items",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class PayoutSummarySerializer(serializers.ModelSerializer):
    """Lightweight serializer for payout list view"""

    seller_username = serializers.CharField(source="seller.username", read_only=True)
    formatted_amount = serializers.CharField(source="amount_formatted", read_only=True)
    is_completed = serializers.BooleanField(read_only=True)
    is_failed = serializers.BooleanField(read_only=True)
    days_since_created = serializers.IntegerField(read_only=True)

    class Meta:
        model = Payout
        fields = [
            "id",
            "stripe_payout_id",
            "seller_username",
            "status",
            "payout_type",
            "amount_decimal",
            "formatted_amount",
            "currency",
            "transfer_count",
            "bank_account_last4",
            "bank_name",
            "arrival_date",
            "is_completed",
            "is_failed",
            "days_since_created",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
