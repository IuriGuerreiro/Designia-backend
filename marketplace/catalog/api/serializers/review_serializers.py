from rest_framework import serializers

from marketplace.catalog.api.serializers.user_serializers import UserSerializer
from marketplace.catalog.domain.models.interaction import ProductReview


class ProductReviewSerializer(serializers.ModelSerializer):
    reviewer = UserSerializer(read_only=True)
    reviewer_name = serializers.CharField(source="reviewer.username", read_only=True)

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

    def validate_rating(self, value):
        if not 1 <= value <= 5:
            raise serializers.ValidationError("Rating must be between 1 and 5")
        return value
