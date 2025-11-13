from rest_framework import serializers

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
