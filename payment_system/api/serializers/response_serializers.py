from rest_framework import serializers

from .payment_serializers import PayoutSerializer, PayoutSummarySerializer


# ==============================================================================
# Payment Flow Responses
# ==============================================================================


class CheckoutSessionResponseSerializer(serializers.Serializer):
    """Response for creating a checkout session"""

    clientSecret = serializers.CharField(help_text="Stripe client secret for embedded checkout")
    sessionId = serializers.CharField(help_text="Stripe checkout session ID", required=False)


class OrderCancellationResponseSerializer(serializers.Serializer):
    """Response for order cancellation"""

    success = serializers.BooleanField()
    message = serializers.CharField()
    refund_requested = serializers.BooleanField()
    refund_amount = serializers.CharField(allow_null=True)
    stripe_refund_id = serializers.CharField(allow_null=True)
    # Order details could be nested here using OrderSerializer if available, or simple dict
    order = serializers.DictField(help_text="Updated order details")


# ==============================================================================
# Stripe Connect Responses
# ==============================================================================


class StripeAccountStatusResponseSerializer(serializers.Serializer):
    """Response for Stripe account status"""

    has_account = serializers.BooleanField()  # Renamed from has_stripe_account in view logic sometimes, need to align
    has_stripe_account = serializers.BooleanField(
        required=False
    )  # View uses has_stripe_account in get_stripe_account_status
    account_id = serializers.CharField(allow_null=True)
    status = serializers.CharField()
    details_submitted = serializers.BooleanField(required=False)
    charges_enabled = serializers.BooleanField(required=False)
    payouts_enabled = serializers.BooleanField(required=False)
    requirements = serializers.DictField(required=False)
    message = serializers.CharField(required=False)
    account_created = serializers.BooleanField(required=False)
    next_step = serializers.CharField(required=False)
    eligible_for_creation = serializers.BooleanField(required=False)
    eligibility_errors = serializers.ListField(child=serializers.CharField(), required=False)


class StripeAccountSessionResponseSerializer(serializers.Serializer):
    """Response for creating an account session"""

    message = serializers.CharField()
    client_secret = serializers.CharField()
    account_id = serializers.CharField()


class TransferResponseSerializer(serializers.Serializer):
    """Response for payment transfer"""

    success = serializers.BooleanField()
    message = serializers.CharField()
    transfer_details = serializers.DictField()
    currency_info = serializers.DictField()
    transaction_details = serializers.DictField()
    balance_summary = serializers.DictField()
    exchange_rate_info = serializers.DictField()


# ==============================================================================
# Payout & Holds Responses
# ==============================================================================


class PaymentHoldsResponseSerializer(serializers.Serializer):
    """Response for seller payment holds"""

    success = serializers.BooleanField()
    summary = serializers.DictField(help_text="Summary statistics")
    holds = serializers.ListField(help_text="List of held transactions")
    message = serializers.CharField()
    debug_info = serializers.DictField(required=False)


class PayoutListResponseSerializer(serializers.Serializer):
    """Response for listing payouts"""

    payouts = PayoutSummarySerializer(many=True)
    pagination = serializers.DictField()
    summary = serializers.DictField(required=False)  # For admin view


class PayoutDetailResponseSerializer(serializers.Serializer):
    """Response for payout detail"""

    payout = PayoutSerializer()


class PayoutOrdersResponseSerializer(serializers.Serializer):
    """Response for payout orders"""

    payout_id = serializers.CharField()
    payout_amount = serializers.CharField()
    payout_status = serializers.CharField()
    transfer_count = serializers.IntegerField()
    orders = serializers.ListField()


# ==============================================================================
# Analytics & Admin Responses
# ==============================================================================


class PayoutAnalyticsResponseSerializer(serializers.Serializer):
    """Response for payout analytics"""

    summary = serializers.DictField()
    financial_metrics = serializers.DictField()
    performance_metrics = serializers.DictField()
    reconciliation_status = serializers.DictField()
    recent_activity = serializers.DictField()
    error_analysis = serializers.DictField()
    tracking_capabilities = serializers.DictField()


class PerformanceReportResponseSerializer(serializers.Serializer):
    """Response for performance report"""

    report_metadata = serializers.DictField()
    processing_performance = serializers.DictField()
    query_performance = serializers.DictField()
    error_analysis = serializers.DictField()
    retry_analysis = serializers.DictField()
    recommendations = serializers.ListField(child=serializers.CharField())


class ReconciliationUpdateResponseSerializer(serializers.Serializer):
    """Response for reconciliation update"""

    success = serializers.BooleanField()
    payout_id = serializers.CharField()
    reconciliation_update = serializers.DictField()
    performance_metrics = serializers.DictField()
    status_history = serializers.DictField()


class AdminTransactionListResponseSerializer(serializers.Serializer):
    """Response for admin transaction list"""

    transactions = serializers.ListField()
    pagination = serializers.DictField()
    summary = serializers.DictField()


# ==============================================================================
# Internal API Responses
# ==============================================================================


class InternalPaymentStatusResponseSerializer(serializers.Serializer):
    """Response for internal payment status"""

    order_id = serializers.CharField()
    payment_status = serializers.CharField()
    order_current_status = serializers.CharField()
    cached = serializers.BooleanField()


class InternalSellerBalanceResponseSerializer(serializers.Serializer):
    """Response for internal seller balance"""

    seller_id = serializers.CharField()
    available_balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    pending_balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.CharField()
    cached = serializers.BooleanField()


class ErrorResponseSerializer(serializers.Serializer):
    """Standard error response"""

    error = serializers.CharField()
    detail = serializers.CharField(required=False)
