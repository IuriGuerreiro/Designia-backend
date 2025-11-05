from rest_framework import serializers

from .models import ActivitySummary, UserClick


class UserClickSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    user_email = serializers.CharField(source="user.email", read_only=True)

    class Meta:
        model = UserClick
        fields = [
            "id",
            "product",
            "product_name",
            "action",
            "user",
            "user_email",
            "session_key",
            "ip_address",
            "created_at",
        ]
        read_only_fields = ["id", "created_at", "product_name", "user_email"]


class ActivityTrackingSerializer(serializers.Serializer):
    """Serializer for activity tracking requests"""

    product_id = serializers.UUIDField()
    action = serializers.ChoiceField(choices=UserClick.ACTION_CHOICES)

    def validate_action(self, value):
        """Validate action is in allowed choices"""
        valid_actions = [choice[0] for choice in UserClick.ACTION_CHOICES]
        if value not in valid_actions:
            raise serializers.ValidationError(f"Invalid action. Must be one of: {', '.join(valid_actions)}")
        return value


class ActivitySummarySerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    # Calculated conversion rates
    view_to_click_rate = serializers.SerializerMethodField()
    click_to_cart_rate = serializers.SerializerMethodField()
    favorite_to_unfavorite_ratio = serializers.SerializerMethodField()

    class Meta:
        model = ActivitySummary
        fields = [
            "id",
            "product",
            "product_name",
            "period_type",
            "period_start",
            "period_end",
            "total_views",
            "total_clicks",
            "total_favorites",
            "total_unfavorites",
            "total_cart_additions",
            "total_cart_removals",
            "unique_users",
            "unique_sessions",
            "view_to_click_rate",
            "click_to_cart_rate",
            "favorite_to_unfavorite_ratio",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "product_name"]

    def get_view_to_click_rate(self, obj):
        """Calculate view to click conversion rate"""
        if obj.total_views > 0:
            return round((obj.total_clicks / obj.total_views) * 100, 2)
        return 0.0

    def get_click_to_cart_rate(self, obj):
        """Calculate click to cart conversion rate"""
        if obj.total_clicks > 0:
            return round((obj.total_cart_additions / obj.total_clicks) * 100, 2)
        return 0.0

    def get_favorite_to_unfavorite_ratio(self, obj):
        """Calculate favorite to unfavorite ratio"""
        if obj.total_unfavorites > 0:
            return round(obj.total_favorites / obj.total_unfavorites, 2)
        return obj.total_favorites if obj.total_favorites > 0 else 0.0


class ProductActivityStatsSerializer(serializers.Serializer):
    """Serializer for product activity statistics response"""

    product_id = serializers.UUIDField()
    product_name = serializers.CharField()

    # Activity counts
    view_count = serializers.IntegerField()
    click_count = serializers.IntegerField()
    favorite_count = serializers.IntegerField()
    unfavorite_count = serializers.IntegerField()
    cart_add_count = serializers.IntegerField()
    cart_remove_count = serializers.IntegerField()

    # Product metrics (if available)
    total_views = serializers.IntegerField(required=False)
    total_clicks = serializers.IntegerField(required=False)
    total_favorites = serializers.IntegerField(required=False)
    total_cart_additions = serializers.IntegerField(required=False)
    view_to_click_rate = serializers.FloatField(required=False)
    click_to_cart_rate = serializers.FloatField(required=False)
    cart_to_purchase_rate = serializers.FloatField(required=False)
    last_updated = serializers.DateTimeField(required=False)
