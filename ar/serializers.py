from rest_framework import serializers

from marketplace.models import ProductImage
from utils.s3_storage import S3StorageError, get_s3_storage

from .models import ProductARModel


class ProductARModelSerializer(serializers.ModelSerializer):
    """Read-only serializer exposing metadata about a product 3D model."""

    product_id = serializers.UUIDField(source="product.id", read_only=True)
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = ProductARModel
        fields = [
            "id",
            "product_id",
            "s3_key",
            "s3_bucket",
            "original_filename",
            "file_size",
            "content_type",
            "uploaded_by",
            "uploaded_at",
            "updated_at",
            "last_download_requested_at",
            "download_url",
        ]
        read_only_fields = fields

    def get_download_url(self, obj):
        """
        Return a presigned URL if the serializer context requests it.
        We only generate the URL when `include_download_url` is truthy to avoid
        unnecessary presigned URL generation.
        """
        include_download = self.context.get("include_download_url")
        request = self.context.get("request")
        if include_download is None and request:
            include_download = request.query_params.get("include_download_url")

        if not include_download:
            return None

        expires_in = self.context.get("download_ttl", 900)

        try:
            storage = get_s3_storage()
            return storage.download_product_3d_model(obj.s3_key, as_url=True, expires_in=expires_in)
        except S3StorageError:
            return None


class ProductARModelUploadSerializer(serializers.Serializer):
    """Input serializer for uploading/replacing a product 3D model."""

    product_id = serializers.UUIDField()
    model_file = serializers.FileField()

    def validate_model_file(self, value):
        max_size = 150 * 1024 * 1024  # 150MB
        if value.size and value.size > max_size:
            raise serializers.ValidationError("3D model must be smaller than 150MB.")
        return value


class ProductARCatalogSerializer(ProductARModelSerializer):
    """Expanded serializer including product metadata for admin/AR catalog."""

    product = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()

    class Meta(ProductARModelSerializer.Meta):
        fields = ProductARModelSerializer.Meta.fields + [
            "product",
        ]

    def get_product(self, obj):
        product = obj.product
        primary_image = self._get_primary_image(product)
        return {
            "id": str(product.id),
            "name": product.name,
            "slug": product.slug,
            "short_description": product.short_description,
            "price": str(product.price),
            "brand": product.brand,
            "model": product.model,
            "category": product.category.name if product.category else None,
            "primary_image": primary_image,
        }

    def get_download_url(self, obj):
        try:
            storage = get_s3_storage()
            return storage.download_product_3d_model(
                obj.s3_key, as_url=True, expires_in=self.context.get("download_ttl", 900)
            )
        except S3StorageError:
            return None

    def _get_primary_image(self, product):
        images = getattr(product, "_cached_images", None)
        if images is None and hasattr(product, "images"):
            images = list(product.images.all())
            product._cached_images = images
        elif images is None:
            images = list(ProductImage.objects.filter(product=product))

        primary = next((img for img in images if img.is_primary), None)
        image = primary or (images[0] if images else None)
        if not image:
            return None
        return image.get_proxy_url() or image.get_presigned_url()
