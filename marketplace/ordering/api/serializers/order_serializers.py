from rest_framework import serializers

from marketplace.catalog.api.serializers.user_serializers import UserSerializer
from marketplace.ordering.domain.models.order import Order, OrderItem, OrderShipping


class OrderItemSerializer(serializers.ModelSerializer):
    product_image_fresh = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = [
            "id",
            "product",
            "seller",
            "quantity",
            "unit_price",
            "total_price",
            "product_name",
            "product_description",
            "product_image",
            "product_image_fresh",
        ]
        read_only_fields = ["id", "total_price"]

    def get_product_image_fresh(self, obj):
        try:
            # We assume product still exists, but handle errors gracefully
            if not obj.product:
                return None
            primary_image = obj.product.images.filter(is_primary=True).first()
            if not primary_image:
                primary_image = obj.product.images.order_by("order").first()
            if primary_image:
                return primary_image.get_proxy_url()
            return None
        except Exception:
            return None


class OrderShippingSerializer(serializers.ModelSerializer):
    seller = UserSerializer(read_only=True)

    class Meta:
        model = OrderShipping
        fields = [
            "id",
            "seller",
            "tracking_number",
            "shipping_carrier",
            "carrier_code",
            "shipped_at",
            "delivered_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "seller", "created_at", "updated_at"]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    buyer = UserSerializer(read_only=True)
    shipping_info = OrderShippingSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "buyer",
            "status",
            "payment_status",
            "subtotal",
            "shipping_cost",
            "tax_amount",
            "discount_amount",
            "total_amount",
            "shipping_address",
            "tracking_number",
            "shipping_carrier",
            "carrier_code",
            "items",
            "shipping_info",
            "buyer_notes",
            "cancellation_reason",
            "cancelled_by",
            "cancelled_at",
            "processed_at",
            "created_at",
            "updated_at",
            "shipped_at",
            "delivered_at",
        ]
        read_only_fields = ["id", "buyer", "created_at", "updated_at", "cancelled_by", "cancelled_at", "processed_at"]

    def validate_shipping_address(self, value):
        required_fields = ["street", "city", "state", "postal_code", "country"]
        for field in required_fields:
            if field not in value:
                raise serializers.ValidationError(f"Shipping address must include {field}")
        return value
