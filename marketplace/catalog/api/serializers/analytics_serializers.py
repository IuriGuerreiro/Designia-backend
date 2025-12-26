from rest_framework import serializers


class OrdersByStatusSerializer(serializers.Serializer):
    """Serializer for order counts by status"""

    pending_payment = serializers.IntegerField()
    payment_confirmed = serializers.IntegerField()
    awaiting_shipment = serializers.IntegerField()
    shipped = serializers.IntegerField()
    delivered = serializers.IntegerField()
    cancelled = serializers.IntegerField()
    refunded = serializers.IntegerField()
    return_requested = serializers.IntegerField()


class TopProductSerializer(serializers.Serializer):
    """Serializer for top performing products"""

    id = serializers.UUIDField()
    name = serializers.CharField()
    slug = serializers.SlugField()
    total_sold = serializers.IntegerField()
    revenue = serializers.DecimalField(max_digits=10, decimal_places=2)
    views = serializers.IntegerField()


class RecentOrderSerializer(serializers.Serializer):
    """Serializer for recent order summary"""

    id = serializers.UUIDField()
    buyer_username = serializers.CharField()
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    status = serializers.CharField()
    created_at = serializers.DateTimeField()
    items_count = serializers.IntegerField()


class SellerAnalyticsSerializer(serializers.Serializer):
    """Main serializer for seller dashboard analytics"""

    # Overview metrics
    total_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_orders = serializers.IntegerField()
    total_products = serializers.IntegerField()
    active_products = serializers.IntegerField()
    total_items_sold = serializers.IntegerField()

    # Product metrics
    total_views = serializers.IntegerField()
    total_clicks = serializers.IntegerField()
    total_favorites = serializers.IntegerField()

    # Conversion rates
    view_to_click_rate = serializers.FloatField()
    click_to_sale_rate = serializers.FloatField()

    # Orders breakdown
    orders_by_status = OrdersByStatusSerializer()
    pending_fulfillment_count = serializers.IntegerField()

    # Top products and recent orders
    top_products = TopProductSerializer(many=True)
    recent_orders = RecentOrderSerializer(many=True)

    # Period info (for filtering)
    period_start = serializers.DateTimeField(allow_null=True)
    period_end = serializers.DateTimeField(allow_null=True)
