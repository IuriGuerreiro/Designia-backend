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

    @extend_schema(
        operation_id="products_list",
        summary="List products with filters",
        description="""
        **What it receives:**
        - Query parameters for filtering (category, seller, price range, condition, brand, stock status)
        - Pagination parameters (page, page_size)
        - Ordering parameter

        **What it returns:**
        - Paginated list of products
        - Total count and page information
        """,
        parameters=[
            OpenApiParameter(name="category", type=str, description="Filter by category slug"),
            OpenApiParameter(name="seller", type=int, description="Filter by seller ID"),
            OpenApiParameter(name="price_min", type=float, description="Minimum price"),
            OpenApiParameter(name="price_max", type=float, description="Maximum price"),
            OpenApiParameter(name="condition", type=str, description="Product condition (new, used, etc.)"),
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

        # Extract filters
        filters = {}
        # Mapping query params to filters
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

        # Serialize products
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
        description="""
        **What it receives:**
        - `slug` (string in URL): Product slug identifier

        **What it returns:**
        - Complete product details including:
          - Full product information
          - Array of images with proxy URLs
          - Array of reviews with reviewer info
          - Seller info (id, username, rating)
          - Category info
        - View count is automatically incremented
        """,
        responses={
            200: ProductDetailSerializer,
            404: OpenApiResponse(response=ErrorResponseSerializer, description="Product not found"),
            500: OpenApiResponse(response=ErrorResponseSerializer, description="Internal server error"),
        },
        tags=["Marketplace - Products"],
    )
    def retrieve(self, request, slug=None):
        service = self.get_service()

        # We need product ID but we have slug.
        # Service `get_product` expects ID.
        # We should probably update service to accept slug or lookup ID here.
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
        description="""
        **What it receives:**
        - Product data (name, description, price, category, stock, etc.)
        - Product images via multipart/form-data (any field name, e.g., 'uploaded_images', 'images', etc.)
        - Optional `image_metadata` (JSON string) with format:
          ```json
          {
            "filename.jpg": {
              "alt_text": "Image description",
              "is_primary": true,
              "order": 0
            }
          }
          ```
        - Authentication token (must be a seller)

        **What it returns:**
        - Created product with generated ID and slug
        - All uploaded images with their metadata (alt_text, is_primary, order)

        **Example:**
        Upload images with metadata to control display order and primary image selection.
        """,
        request=ProductCreateUpdateSerializer,
        responses={
            201: OpenApiResponse(response=ProductDetailSerializer, description="Product created successfully"),
            400: OpenApiResponse(response=ErrorResponseSerializer, description="Invalid data"),
            403: OpenApiResponse(response=ErrorResponseSerializer, description="Permission denied (not a seller)"),
        },
        tags=["Marketplace - Products"],
    )
    def create(self, request):
        import base64
        import io
        import logging

        from django.core.files.uploadedfile import InMemoryUploadedFile

        logger = logging.getLogger(__name__)
        service = self.get_service()

        # Validate input using serializer
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        # Handle base64-encoded images from image_data
        images = []
        image_metadata = {}

        image_data_list = data.pop("image_data", [])
        for img_data in image_data_list:
            try:
                # Extract base64 content (remove data URI prefix if present)
                image_content = img_data.get("image_content", "")
                if "," in image_content:
                    # Format: "data:image/png;base64,iVBORw0KGgo..."
                    header, encoded = image_content.split(",", 1)
                else:
                    encoded = image_content

                # Decode base64
                image_bytes = base64.b64decode(encoded)

                # Determine content type
                content_type = "image/jpeg"  # Default
                if "data:" in image_content:
                    # Extract from data URI
                    parts = image_content.split(";")[0].split(":")
                    if len(parts) > 1:
                        content_type = parts[1]

                # Create in-memory file
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

                # Build metadata
                image_metadata[filename] = {
                    "alt_text": img_data.get("alt_text", ""),
                    "is_primary": img_data.get("is_primary", False),
                    "order": img_data.get("order", len(images) - 1),
                }

            except Exception as e:
                logger.error(f"Error decoding image: {e}")
                continue

        result = service.create_product(data, request.user, images, image_metadata)

        if not result.ok:
            if result.error == ErrorCodes.PERMISSION_DENIED:
                return Response({"detail": result.error_detail}, status=status.HTTP_403_FORBIDDEN)
            return Response({"detail": result.error_detail}, status=status.HTTP_400_BAD_REQUEST)

        return Response(self.get_serializer(result.value).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        operation_id="products_update",
        summary="Update product (Owner only)",
        description="""
        **What it receives:**
        - `slug` (string in URL): Product to update
        - Complete product data (all fields required)
        - Authentication token (must be product owner)

        **What it returns:**
        - Updated product details
        """,
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

        # Validate input
        serializer = self.get_serializer(product, data=request.data, partial=False)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        result = service.update_product(str(product.id), serializer.validated_data, request.user)

        if not result.ok:
            if result.error == ErrorCodes.NOT_PRODUCT_OWNER:
                return Response({"detail": result.error_detail}, status=status.HTTP_403_FORBIDDEN)
            return Response({"detail": result.error_detail}, status=status.HTTP_400_BAD_REQUEST)

        return Response(self.get_serializer(result.value).data)

    @extend_schema(
        operation_id="products_partial_update",
        summary="Partially update product (Owner only)",
        description="""
        **What it receives:**
        - `slug` (string in URL): Product to update
        - Partial product data (only fields to update)
        - Authentication token (must be product owner)

        **What it returns:**
        - Updated product details
        """,
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

        result = service.update_product(str(product.id), serializer.validated_data, request.user)

        if not result.ok:
            if result.error == ErrorCodes.NOT_PRODUCT_OWNER:
                return Response({"detail": result.error_detail}, status=status.HTTP_403_FORBIDDEN)
            return Response({"detail": result.error_detail}, status=status.HTTP_400_BAD_REQUEST)

        return Response(self.get_serializer(result.value).data)

    @extend_schema(
        operation_id="products_delete",
        summary="Delete product (Owner only)",
        description="""
        **What it receives:**
        - `slug` (string in URL): Product to delete
        - Authentication token (must be product owner)

        **What it returns:**
        - 204 No Content on success
        """,
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
        description="""
        **What it receives:**
        - Authentication token (must be a seller)
        - Pagination parameters (page, page_size)

        **What it returns:**
        - Paginated list of products owned by current user
        """,
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
        """Get current user's products with pagination"""
        service = self.get_service()

        # Add pagination support
        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 20))
        ordering = request.query_params.get("ordering", "-created_at")

        # Using list_products with seller filter
        result = service.list_products(
            filters={"seller": request.user.id}, page=page, page_size=page_size, ordering=ordering
        )

        if not result.ok:
            return Response({"detail": result.error_detail}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Serialize products
        serializer = self.get_serializer(result.value["results"], many=True)

        # Return paginated response matching standard list format
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
        description="""
        **What it receives:**
        - Authentication token

        **What it returns:**
        - List of products marked as favorites by current user
        """,
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
        """Get user's favorite products"""
        if not request.user.is_authenticated:
            return Response({"detail": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)

        favorites = ProductFavorite.objects.filter(user=request.user).select_related("product")
        serializer = ProductFavoriteSerializer(favorites, many=True, context={"request": request})
        return Response(serializer.data)

    @extend_schema(
        operation_id="products_toggle_favorite",
        summary="Toggle product favorite status",
        description="""
        **What it receives:**
        - `slug` (string in URL): Product to favorite/unfavorite
        - Authentication token

        **What it returns:**
        - `{"favorited": true}` if product was added to favorites
        - `{"favorited": false}` if product was removed from favorites
        """,
        responses={
            200: OpenApiResponse(description="Favorite status toggled"),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="Authentication required"),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="Product not found"),
        },
        tags=["Marketplace - Products"],
    )
    @action(detail=True, methods=["post"])
    def favorite(self, request, slug=None):
        """Toggle favorite status"""
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
