import logging

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from marketplace.models import Product
from marketplace.permissions import IsAdminUser, IsSellerUser
from utils.s3_storage import S3StorageError, get_s3_storage

from .models import ProductARModel, ProductARModelDownload
from .serializers import (
    ProductARCatalogSerializer,
    ProductARModelDownloadSerializer,
    ProductARModelSerializer,
    ProductARModelUploadSerializer,
)


logger = logging.getLogger(__name__)


class ProductARModelViewSet(viewsets.GenericViewSet):
    """
    API endpoints that allow sellers to upload a single 3D model per product
    and authenticated users to request download URLs.
    """

    queryset = ProductARModel.objects.select_related("product", "uploaded_by")
    serializer_class = ProductARModelSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    lookup_field = "pk"  # use product UUID in the router path

    def get_permissions(self):
        if self.action in {"create"}:
            return [permissions.IsAuthenticated(), IsSellerUser()]
        if self.action in {"download_link"}:
            return [permissions.IsAuthenticated()]
        return super().get_permissions()

    # Helpers -----------------------------------------------------------------
    def _get_model_for_product(self, product_id):
        return get_object_or_404(ProductARModel, product__id=product_id)

    def _get_product_for_upload(self, product_id):
        return get_object_or_404(Product, id=product_id)

    # Actions -----------------------------------------------------------------
    def create(self, request, *args, **kwargs):
        """Upload or replace a product's 3D model."""
        serializer = ProductARModelUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        product = self._get_product_for_upload(serializer.validated_data["product_id"])

        if product.seller != request.user and not request.user.is_staff:
            raise PermissionDenied("You can only upload 3D models for your own products.")

        model_file = serializer.validated_data["model_file"]

        storage = get_s3_storage()

        try:
            upload_result = storage.upload_product_3d_model(
                product_id=str(product.id),
                model_file=model_file,
                user_id=str(request.user.id),
            )
        except S3StorageError as exc:
            logger.error("Failed to upload 3D model for product %s: %s", product.id, exc)
            raise ValidationError({"model_file": str(exc)}) from exc

        # Remove previous file if one already exists
        existing = getattr(product, "ar_model", None)
        if existing and existing.s3_key and existing.s3_key != upload_result["key"]:
            try:
                storage.delete_file(existing.s3_key)
            except S3StorageError as exc:
                logger.warning("Could not delete previous 3D model %s: %s", existing.s3_key, exc)

        ar_model, _created = ProductARModel.objects.update_or_create(
            product=product,
            defaults={
                "s3_key": upload_result["key"],
                "s3_bucket": upload_result.get("bucket", storage.bucket_name),
                "original_filename": getattr(model_file, "name", upload_result["key"].split("/")[-1]),
                "file_size": upload_result.get("size"),
                "content_type": upload_result.get("content_type"),
                "uploaded_by": request.user,
            },
        )

        output = ProductARModelSerializer(
            ar_model,
            context={**self.get_serializer_context(), "include_download_url": True},
        )
        return Response(output.data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, pk=None):
        """Get metadata for a product's 3D model using the product UUID as lookup."""
        ar_model = self._get_model_for_product(pk)
        serializer = self.get_serializer(ar_model)
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path="download-link")
    def download_link(self, request, pk=None):
        """Generate a fresh presigned download link for the product's 3D model."""
        ar_model = self._get_model_for_product(pk)

        try:
            ttl = int(request.query_params.get("ttl", 900))
        except (TypeError, ValueError):
            ttl = 900

        ttl = max(300, min(ttl, 3600))

        storage = get_s3_storage()

        try:
            download_url = storage.download_product_3d_model(ar_model.s3_key, as_url=True, expires_in=ttl)
        except S3StorageError as exc:
            logger.error("Failed to create download URL for 3D model %s: %s", ar_model.id, exc)
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        ar_model.last_download_requested_at = timezone.now()
        ar_model.save(update_fields=["last_download_requested_at"])

        return Response({"download_url": download_url, "expires_in": ttl})

    @action(detail=False, methods=["get"], url_path="catalog", permission_classes=[IsAdminUser])
    def catalog(self, request):
        """Return catalog of products with AR models for admin/AR tooling."""
        queryset = (
            self.get_queryset()
            .select_related("product", "uploaded_by", "product__category")
            .prefetch_related("product__images")
            .order_by("-uploaded_at")
        )

        serializer = ProductARCatalogSerializer(
            queryset,
            many=True,
            context={**self.get_serializer_context(), "include_download_url": True},
        )
        return Response(serializer.data)


class ProductARModelDownloadViewSet(viewsets.ModelViewSet):
    """
    CRUD operations for tracking the models a user has downloaded.
    Users only see and manage their own download records.
    """

    serializer_class = ProductARModelDownloadSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            ProductARModelDownload.objects.filter(user=self.request.user)
            .select_related("product_model__product")
            .order_by("-created_at")
        )

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
