from django.contrib.auth import get_user_model
from rest_framework import serializers


User = get_user_model()


class MinimalSellerSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username"]
        read_only_fields = ["id"]


class ProductDetailSellerSerializer(serializers.ModelSerializer):
    """Minimal seller info for product detail endpoint"""

    seller_rating = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "seller_rating"]
        read_only_fields = ["id", "username"]

    def get_seller_rating(self, obj):
        # Return average rating from seller's products reviews
        # Placeholder implementation - adjust based on your review system
        if hasattr(obj, "average_seller_rating"):
            return obj.average_seller_rating
        return None


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "avatar"]
        read_only_fields = ["id"]
