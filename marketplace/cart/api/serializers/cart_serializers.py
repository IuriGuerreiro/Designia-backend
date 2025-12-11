from rest_framework import serializers

from marketplace.cart.domain.models.cart import CartItem
from marketplace.catalog.api.serializers.product_serializers import ProductListSerializer


class CartItemSerializer(serializers.ModelSerializer):
    product_id = serializers.CharField(write_only=True)
    product = ProductListSerializer(read_only=True)

    class Meta:
        model = CartItem
        fields = ["id", "product", "product_id", "quantity", "added_at"]
        read_only_fields = ["id", "product", "added_at"]

    def create(self, validated_data):
        raise NotImplementedError

    def update(self, instance, validated_data):
        raise NotImplementedError


class CartItemServiceOutputSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    product = ProductListSerializer(read_only=True)
    quantity = serializers.IntegerField()
    added_at = serializers.DateTimeField(read_only=True)


class CartServiceOutputSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    user_id = serializers.IntegerField(read_only=True)
    items = CartItemServiceOutputSerializer(many=True, read_only=True)
    items_count = serializers.IntegerField(read_only=True)
    totals = serializers.JSONField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class CartSerializer(serializers.ModelSerializer):
    # This might be deprecated if we use service output exclusively
    pass
