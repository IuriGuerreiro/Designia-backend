from django.conf import settings
from rest_framework import serializers

from marketplace.catalog.domain.models.catalog import ProductImage


class ProductDetailImageSerializer(serializers.ModelSerializer):
    """Minimal image info for product detail endpoint"""

    image = serializers.SerializerMethodField()
    url = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = [
            "id",
            "image",
            "alt_text",
            "is_primary",
            "order",
            "url",
        ]
        read_only_fields = ["id"]

    def get_image(self, obj):
        """Return original filename for reference"""
        return obj.original_filename or ""

    def get_url(self, obj):
        """Return proxy URL for the image"""
        return obj.get_proxy_url()


class ProductImageSerializer(serializers.ModelSerializer):
    presigned_url = serializers.SerializerMethodField()
    proxy_url = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = [
            "id",
            "alt_text",
            "is_primary",
            "order",
            "presigned_url",
            "proxy_url",
            "image_url",
            "s3_key",
            "original_filename",
            "file_size",
            "content_type",
        ]
        read_only_fields = ["id", "s3_key", "original_filename", "file_size", "content_type"]

    def get_presigned_url(self, obj):
        if getattr(settings, "S3_USE_PROXY_FOR_IMAGE_LINKS", True):
            return obj.get_proxy_url()
        return obj.get_presigned_url(expires_in=3600)

    def get_proxy_url(self, obj):
        return obj.get_proxy_url()

    def get_image_url(self, obj):
        return obj.get_proxy_url()
