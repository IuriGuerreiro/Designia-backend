import base64
import io
import logging
import os

from django.core.files.uploadedfile import InMemoryUploadedFile
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response

from infrastructure.container import container
from marketplace.api.serializers import ErrorResponseSerializer
from marketplace.models import Product, ProductFavorite
from marketplace.permissions import IsSellerOrReadOnly, IsSellerUser
from marketplace.serializers import (
    ProductCreateUpdateSerializer,
    ProductDetailSerializer,
    ProductFavoriteSerializer,
    ProductListSerializer,
)
from marketplace.services import CatalogService, ErrorCodes


# Try imports for optional AR dependencies
try:
    from ar.models import ProductARModel
except ImportError:
    ProductARModel = None

try:
    from utils.s3_storage import S3StorageError, get_s3_storage
except ImportError:
    get_s3_storage = None
    S3StorageError = Exception

logger = logging.getLogger(__name__)


class ProductViewSet(viewsets.ModelViewSet):
    """
    ViewSet for products with full CRUD operations using Service Layer.
    """

    permission_classes = [IsAuthenticatedOrReadOnly]
    lookup_field = "slug"
    queryset = Product.objects.all()

    def get_service(self) -> CatalogService:
        return container.catalog_service()

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return ProductCreateUpdateSerializer
        elif self.action == "retrieve":
            return ProductDetailSerializer
        return ProductListSerializer

    def get_permissions(self):
        if self.action in ["create", "my_products"]:
            return [IsAuthenticated(), IsSellerUser()]
        elif self.action in ["update", "partial_update", "destroy"]:
            return [IsAuthenticated(), IsSellerOrReadOnly()]
        return super().get_permissions()

    def _handle_ar_model_update(self, product, model_data, user):
        """
        Handle AR model update: upload new, or delete existing.
        model_data: Dict with 'model_content' and 'filename', or None (to delete).
        """
        if ProductARModel is None:
            logger.warning("AR app not available, skipping AR model update")
            return

        # Case 1: Delete existing model
        if model_data is None:
            # If explicit None was passed (user wants to remove), delete existing
            ProductARModel.objects.filter(product=product).delete()
            logger.info(f"Deleted AR model for product {product.id}")
            return

        # Case 2: Upload new model
        try:
            # Extract base64 content
            model_content = model_data.get("model_content", "")
            if "," in model_content:
                header, encoded = model_content.split(",", 1)
            else:
                encoded = model_content

            # Decode base64
            model_bytes = base64.b64decode(encoded)

            # Determine content type
            content_type = "model/gltf-binary"  # Default for .glb
            filename = model_data.get("filename", "model.glb")

            if filename.lower().endswith(".gltf"):
                content_type = "model/gltf+json"
            elif filename.lower().endswith(".usdz"):
                content_type = "model/vnd.usdz+zip"

            # Create in-memory file
            model_file = InMemoryUploadedFile(
                file=io.BytesIO(model_bytes),
                field_name="model_file",
                name=filename,
                content_type=content_type,
                size=len(model_bytes),
                charset=None,
            )

            # Validate
            max_size = 50 * 1024 * 1024  # 50MB
            allowed_extensions = [".glb", ".gltf", ".usdz"]
            file_ext = os.path.splitext(filename)[1].lower()

            if model_file.size > max_size:
                logger.warning(f"3D model file too large: {model_file.size} bytes")
                return
            if file_ext not in allowed_extensions:
                logger.warning(f"Invalid 3D model extension: {file_ext}")
                return

            # Delete old model first (optional, but good for cleanup)
            ProductARModel.objects.filter(product=product).delete()

            # Upload to S3
            storage = get_s3_storage()
            upload_result = storage.upload_product_3d_model(
                product_id=str(product.id),
                model_file=model_file,
                user_id=str(user.id),
            )

            # Create DB entry
            ProductARModel.objects.create(
                product=product,
                s3_key=upload_result["key"],
                s3_bucket=upload_result.get("bucket", storage.bucket_name),
                original_filename=filename,
                file_size=upload_result.get("size"),
                content_type=upload_result.get("content_type"),
                uploaded_by=user,
            )
            logger.info(f"Uploaded 3D model for product {product.id}: {filename}")

        except Exception as e:
            logger.error(f"Error processing 3D model: {e}", exc_info=True)

    @extend_schema(
        operation_id="products_list",
        summary="List products with filters",
        description="List products with various filters.",
        parameters=[
            OpenApiParameter(name="category", type=str, description="Filter by category slug"),
            OpenApiParameter(name="seller", type=int, description="Filter by seller ID"),
            OpenApiParameter(name="price_min", type=float, description="Minimum price"),
            OpenApiParameter(name="price_max", type=float, description="Maximum price"),
            OpenApiParameter(name="condition", type=str, description="Product condition"),
            OpenApiParameter(name="brand", type=str, description="Filter by brand"),
            OpenApiParameter(name="in_stock", type=bool, description="Only show in-stock products"),
            OpenApiParameter(name="is_featured", type=bool, description="Only show featured products"),
            OpenApiParameter(name="page", type=int, description="Page number (default: 1)"),
            OpenApiParameter(name="page_size", type=int, description="Items per page (default: 20)"),
            OpenApiParameter(name="ordering", type=str, description="Order by field (default: -created_at)"),
        ],
        responses={
            200: OpenApiResponse(
                response=inline_serializer(
                    name="ProductListPaginatedResponse",
                    fields={
                        "count": serializers.IntegerField(),
                        "page": serializers.IntegerField(),
                        "page_size": serializers.IntegerField(),
                        "num_pages": serializers.IntegerField(),
                        "has_next": serializers.BooleanField(),
                        "has_previous": serializers.BooleanField(),
                        "results": ProductListSerializer(many=True),
                    },
                ),
                description="Products retrieved successfully",
            ),
            500: OpenApiResponse(response=ErrorResponseSerializer, description="Internal server error"),
        },
        tags=["Marketplace - Products"],
    )
    def list(self, request, *args, **kwargs):
        service = self.get_service()
        filters = {}
        if request.query_params.get("category"):
            filters["category"] = request.query_params.get("category")
        if request.query_params.get("seller"):
            filters["seller"] = request.query_params.get("seller")
        if request.query_params.get("price_min"):
            filters["price_min"] = request.query_params.get("price_min")
        if request.query_params.get("price_max"):
            filters["price_max"] = request.query_params.get("price_max")
        if request.query_params.get("condition"):
            filters["condition"] = request.query_params.get("condition")
        if request.query_params.get("brand"):
            filters["brand"] = request.query_params.get("brand")
        if request.query_params.get("in_stock"):
            filters["in_stock"] = request.query_params.get("in_stock").lower() == "true"
        if request.query_params.get("is_featured"):
            filters["is_featured"] = request.query_params.get("is_featured").lower() == "true"

        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 20))
        ordering = request.query_params.get("ordering", "-created_at")

        result = service.list_products(filters, page, page_size, ordering)

        if not result.ok:
            return Response({"detail": result.error_detail}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        products = result.value["results"]
        serializer = self.get_serializer(products, many=True)

        response_data = {
            "count": result.value["count"],
            "results": serializer.data,
            "page": result.value["page"],
            "num_pages": result.value["num_pages"],
        }
        return Response(response_data)

    @extend_schema(
        operation_id="products_retrieve",
        summary="Get product details",
        responses={
            200: ProductDetailSerializer,
            404: OpenApiResponse(response=ErrorResponseSerializer, description="Product not found"),
            500: OpenApiResponse(response=ErrorResponseSerializer, description="Internal server error"),
        },
        tags=["Marketplace - Products"],
    )
    def retrieve(self, request, slug=None):
        service = self.get_service()
        try:
            product = Product.objects.get(slug=slug)
        except Product.DoesNotExist:
            return Response({"detail": "Product not found"}, status=status.HTTP_404_NOT_FOUND)

        result = service.get_product(str(product.id), track_view=True)

        if not result.ok:
            if result.error == ErrorCodes.PRODUCT_NOT_FOUND:
                return Response({"detail": result.error_detail}, status=status.HTTP_404_NOT_FOUND)
            return Response({"detail": result.error_detail}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        serializer = self.get_serializer(result.value)
        return Response(serializer.data)

    @extend_schema(
        operation_id="products_create",
        summary="Create a new product (Seller only)",
        request=ProductCreateUpdateSerializer,
        responses={
            201: OpenApiResponse(response=ProductDetailSerializer, description="Product created successfully"),
            400: OpenApiResponse(response=ErrorResponseSerializer, description="Invalid data"),
            403: OpenApiResponse(response=ErrorResponseSerializer, description="Permission denied"),
        },
        tags=["Marketplace - Products"],
    )
    def create(self, request):
        service = self.get_service()
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        # Handle base64-encoded images
        images = []
        image_metadata = {}
        image_data_list = data.pop("image_data", [])

        for img_data in image_data_list:
            try:
                image_content = img_data.get("image_content", "")
                if "," in image_content:
                    header, encoded = image_content.split(",", 1)
                else:
                    encoded = image_content

                image_bytes = base64.b64decode(encoded)
                content_type = "image/jpeg"
                if "data:" in image_content:
                    parts = image_content.split(";")[0].split(":")
                    if len(parts) > 1:
                        content_type = parts[1]

                filename = img_data.get("filename", f"image_{len(images)}.jpg")
                image_file = InMemoryUploadedFile(
                    file=io.BytesIO(image_bytes),
                    field_name="image",
                    name=filename,
                    content_type=content_type,
                    size=len(image_bytes),
                    charset=None,
                )
                images.append(image_file)
                image_metadata[filename] = {
                    "alt_text": img_data.get("alt_text", ""),
                    "is_primary": img_data.get("is_primary", False),
                    "order": img_data.get("order", len(images) - 1),
                }
            except Exception as e:
                logger.error(f"Error decoding image: {e}")
                continue

        # Extract model_data to handle after creation
        model_data = data.pop("model_data", None)

        result = service.create_product(data, request.user, images, image_metadata)

        if not result.ok:
            if result.error == ErrorCodes.PERMISSION_DENIED:
                return Response({"detail": result.error_detail}, status=status.HTTP_403_FORBIDDEN)
            return Response({"detail": result.error_detail}, status=status.HTTP_400_BAD_REQUEST)

        product = result.value

        # Handle AR Model
        if model_data:
            self._handle_ar_model_update(product, model_data, request.user)

        response_serializer = ProductDetailSerializer(product, context={"request": request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        operation_id="products_update",
        summary="Update product (Owner only)",
        request=ProductCreateUpdateSerializer,
        responses={
            200: OpenApiResponse(response=ProductDetailSerializer, description="Product updated successfully"),
            400: OpenApiResponse(response=ErrorResponseSerializer, description="Invalid data"),
            403: OpenApiResponse(response=ErrorResponseSerializer, description="Not product owner"),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="Product not found"),
        },
        tags=["Marketplace - Products"],
    )
    def update(self, request, slug=None):
        service = self.get_service()
        try:
            product = Product.objects.get(slug=slug)
        except Product.DoesNotExist:
            return Response({"detail": "Product not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = self.get_serializer(product, data=request.data, partial=False)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Check for model_data in validated_data
        model_data_present = "model_data" in serializer.validated_data
        model_data = serializer.validated_data.pop("model_data", None)

        result = service.update_product(str(product.id), serializer.validated_data, request.user)

        if not result.ok:
            if result.error == ErrorCodes.NOT_PRODUCT_OWNER:
                return Response({"detail": result.error_detail}, status=status.HTTP_403_FORBIDDEN)
            return Response({"detail": result.error_detail}, status=status.HTTP_400_BAD_REQUEST)

        # Handle AR Model Update/Delete if model_data key was present
        if model_data_present:
            self._handle_ar_model_update(product, model_data, request.user)

        response_serializer = ProductDetailSerializer(result.value, context={"request": request})
        return Response(response_serializer.data)

    @extend_schema(
        operation_id="products_partial_update",
        summary="Partially update product (Owner only)",
        request=ProductCreateUpdateSerializer,
        responses={
            200: OpenApiResponse(response=ProductDetailSerializer, description="Product updated successfully"),
            400: OpenApiResponse(response=ErrorResponseSerializer, description="Invalid data"),
            403: OpenApiResponse(response=ErrorResponseSerializer, description="Not product owner"),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="Product not found"),
        },
        tags=["Marketplace - Products"],
    )
    def partial_update(self, request, slug=None):
        service = self.get_service()
        try:
            product = Product.objects.get(slug=slug)
        except Product.DoesNotExist:
            return Response({"detail": "Product not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = self.get_serializer(product, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Check for model_data in validated_data
        model_data_present = "model_data" in serializer.validated_data
        model_data = serializer.validated_data.pop("model_data", None)

        result = service.update_product(str(product.id), serializer.validated_data, request.user)

        if not result.ok:
            if result.error == ErrorCodes.NOT_PRODUCT_OWNER:
                return Response({"detail": result.error_detail}, status=status.HTTP_403_FORBIDDEN)
            return Response({"detail": result.error_detail}, status=status.HTTP_400_BAD_REQUEST)

        # Handle AR Model Update/Delete if model_data key was present
        if model_data_present:
            self._handle_ar_model_update(product, model_data, request.user)

        response_serializer = ProductDetailSerializer(result.value, context={"request": request})
        return Response(response_serializer.data)

    @extend_schema(
        operation_id="products_delete",
        summary="Delete product (Owner only)",
        responses={
            204: OpenApiResponse(description="Product deleted successfully"),
            403: OpenApiResponse(response=ErrorResponseSerializer, description="Not product owner"),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="Product not found"),
        },
        tags=["Marketplace - Products"],
    )
    def destroy(self, request, slug=None):
        service = self.get_service()
        try:
            product = Product.objects.get(slug=slug)
        except Product.DoesNotExist:
            return Response({"detail": "Product not found"}, status=status.HTTP_404_NOT_FOUND)

        result = service.delete_product(str(product.id), request.user)

        if not result.ok:
            if result.error == ErrorCodes.NOT_PRODUCT_OWNER:
                return Response({"detail": result.error_detail}, status=status.HTTP_403_FORBIDDEN)
            return Response({"detail": result.error_detail}, status=status.HTTP_400_BAD_REQUEST)

        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        operation_id="products_my_products",
        summary="Get current user's products (Seller only)",
        parameters=[
            OpenApiParameter(name="page", type=int, description="Page number (default: 1)"),
            OpenApiParameter(name="page_size", type=int, description="Items per page (default: 20)"),
            OpenApiParameter(name="ordering", type=str, description="Order by field (default: -created_at)"),
        ],
        responses={
            200: OpenApiResponse(
                response=inline_serializer(
                    name="MyProductListPaginatedResponse",
                    fields={
                        "count": serializers.IntegerField(),
                        "page": serializers.IntegerField(),
                        "page_size": serializers.IntegerField(),
                        "num_pages": serializers.IntegerField(),
                        "has_next": serializers.BooleanField(),
                        "has_previous": serializers.BooleanField(),
                        "results": ProductListSerializer(many=True),
                    },
                ),
                description="Products retrieved successfully",
            ),
            500: OpenApiResponse(response=ErrorResponseSerializer, description="Internal server error"),
        },
        tags=["Marketplace - Products"],
    )
    @action(detail=False, methods=["get"])
    def my_products(self, request):
        service = self.get_service()
        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 20))
        ordering = request.query_params.get("ordering", "-created_at")

        result = service.list_products(
            filters={"seller": request.user.id}, page=page, page_size=page_size, ordering=ordering
        )

        if not result.ok:
            return Response({"detail": result.error_detail}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        serializer = self.get_serializer(result.value["results"], many=True)
        response_data = {
            "count": result.value["count"],
            "results": serializer.data,
            "page": result.value["page"],
            "num_pages": result.value["num_pages"],
        }
        return Response(response_data)

    @extend_schema(
        operation_id="products_favorites",
        summary="Get user's favorite products",
        responses={
            200: OpenApiResponse(
                response=ProductFavoriteSerializer(many=True), description="Favorites retrieved successfully"
            ),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="Authentication required"),
        },
        tags=["Marketplace - Products"],
    )
    @action(detail=False, methods=["get"])
    def favorites(self, request):
        if not request.user.is_authenticated:
            return Response({"detail": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)

        favorites = ProductFavorite.objects.filter(user=request.user).select_related("product")
        serializer = ProductFavoriteSerializer(favorites, many=True, context={"request": request})
        return Response(serializer.data)

    @extend_schema(
        operation_id="products_toggle_favorite",
        summary="Toggle product favorite status",
        responses={
            200: OpenApiResponse(description="Favorite status toggled"),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="Authentication required"),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="Product not found"),
        },
        tags=["Marketplace - Products"],
    )
    @action(detail=True, methods=["post"])
    def favorite(self, request, slug=None):
        if not request.user.is_authenticated:
            return Response({"detail": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            product = Product.objects.get(slug=slug)
        except Product.DoesNotExist:
            return Response({"detail": "Product not found"}, status=status.HTTP_404_NOT_FOUND)

        favorite, created = ProductFavorite.objects.get_or_create(user=request.user, product=product)

        if not created:
            favorite.delete()
            return Response({"favorited": False})
        return Response({"favorited": True})
