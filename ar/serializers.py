from rest_framework import serializers

from marketplace.models import ProductImage
from utils.s3_storage import S3StorageError, get_s3_storage

from .models import ProductARModel, ProductARModelDownload


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


class ProductARModelDownloadSerializer(serializers.ModelSerializer):
    """Serializer for tracking user downloads of AR models."""

    product_id = serializers.UUIDField(write_only=True, required=False)
    product_model_id = serializers.IntegerField(source="product_model.id", read_only=True)
    product = serializers.SerializerMethodField()

    class Meta:
        model = ProductARModelDownload
        fields = [
            "id",
            "product_model_id",
            "product",
            "product_id",
            "local_path",
            "file_name",
            "file_size",
            "platform",
            "app_version",
            "device_info",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "product_model_id",
            "product",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        product_id = attrs.pop("product_id", None)
        if product_id is not None:
            try:
                attrs["product_model"] = ProductARModel.objects.select_related("product").get(product__id=product_id)
            except ProductARModel.DoesNotExist as exc:
                raise serializers.ValidationError(
                    {"product_id": "No AR model is available for this product."}
                ) from exc
        elif not self.instance:
            raise serializers.ValidationError({"product_id": "This field is required."})
        return super().validate(attrs)

    def get_product(self, obj):
        product = obj.product_model.product
        return {
            "id": str(product.id),
            "name": product.name,
            "slug": product.slug,
        }
