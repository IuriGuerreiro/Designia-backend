from rest_framework import serializers

from marketplace.catalog.domain.models.category import Category


class MinimalCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug"]
        read_only_fields = ["id", "slug"]


class ProductDetailCategorySerializer(serializers.ModelSerializer):
    """Minimal category info for product detail endpoint"""

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "description"]
        read_only_fields = ["id", "slug"]


class CategorySerializer(serializers.ModelSerializer):
    subcategories = serializers.SerializerMethodField()
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "parent",
            "subcategories",
            "product_count",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "slug", "created_at", "subcategories", "product_count"]

    def get_subcategories(self, obj):
        if obj.subcategories.exists():
            return CategorySerializer(obj.subcategories.filter(is_active=True), many=True).data
        return []

    def get_product_count(self, obj):
        if hasattr(obj, "product_count"):
            return obj.product_count
        return obj.products.filter(is_active=True).count()
