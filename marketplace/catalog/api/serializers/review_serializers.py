from rest_framework import serializers

from marketplace.catalog.api.serializers.user_serializers import MinimalSellerSerializer, UserSerializer
from marketplace.catalog.domain.models.interaction import ProductReview


class MinimalProductReviewSerializer(serializers.ModelSerializer):
    """Minimal review info for product detail - no sensitive user data"""

    reviewer = MinimalSellerSerializer(read_only=True, allow_null=True)
    reviewer_display_name = serializers.SerializerMethodField()

    class Meta:
        model = ProductReview
        fields = [
            "id",
            "reviewer",
            "reviewer_display_name",
            "rating",
            "title",
            "comment",
            "is_verified_purchase",
            "created_at",
        ]
        read_only_fields = ["id", "reviewer", "reviewer_display_name", "is_verified_purchase", "created_at"]

    def get_reviewer_display_name(self, obj):
        """Return display name handling deleted users."""
        return obj.get_reviewer_display_name()


class ProductReviewSerializer(serializers.ModelSerializer):
    reviewer = UserSerializer(read_only=True, allow_null=True)
    reviewer_name = serializers.SerializerMethodField()

    class Meta:
        model = ProductReview
        fields = [
            "id",
            "reviewer",
            "reviewer_name",
            "rating",
            "title",
            "comment",
            "is_verified_purchase",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "reviewer", "reviewer_name", "is_verified_purchase", "created_at", "updated_at"]

    def get_reviewer_name(self, obj):
        """Return display name handling deleted users."""
        return obj.get_reviewer_display_name()

    def validate_rating(self, value):
        if not 1 <= value <= 5:
            raise serializers.ValidationError("Rating must be between 1 and 5")
        return value
