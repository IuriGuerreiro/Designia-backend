from rest_framework import serializers


class OrderCancellationRequestSerializer(serializers.Serializer):
    cancellation_reason = serializers.CharField(required=True, help_text="Reason for cancellation")


class StripeAccountCreateRequestSerializer(serializers.Serializer):
    country = serializers.CharField(max_length=2, default="US", help_text="2-letter Country Code (ISO 3166-1 alpha-2)")
    business_type = serializers.ChoiceField(
        choices=["individual", "company"], default="individual", help_text="Type of business"
    )


class TransferRequestSerializer(serializers.Serializer):
    transaction_id = serializers.UUIDField(required=True, help_text="ID of the payment transaction to transfer")
    transfer_group = serializers.CharField(required=False, help_text="Optional transfer group string")


class ReconciliationUpdateRequestSerializer(serializers.Serializer):
    reconciliation_status = serializers.ChoiceField(
        choices=["pending", "matched", "mismatched", "manual_review"],
        required=True,
        help_text="New reconciliation status",
    )
    notes = serializers.CharField(required=False, allow_blank=True, help_text="Optional notes for the update")
