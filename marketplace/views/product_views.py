from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response

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

    def get_service(self) -> CatalogService:
        # Note: We are using CatalogService directly instead of container for now
        # because container support for CatalogService might not be fully set up yet
        # or we want to match existing pattern if container usage is inconsistent.
        # But ideally: return container.catalog_service()
        # Checking container.py... CatalogService is NOT in container.py yet.
        # So we instantiate it directly or add it to container.
        # Given previous steps added services to container, we should probably add this one too
        # or just instantiate it here as done in `views_legacy.py` migration attempts.
        # Let's instantiate directly for now as `CatalogService` is simple.
        return CatalogService()

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

    def create(self, request):
        service = self.get_service()

        # Validate input using serializer (partial validation mostly for fields)
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        # Handle images from request.FILES
        images = []
        for key in request.FILES:
            images.extend(request.FILES.getlist(key))

        result = service.create_product(data, request.user, images)

        if not result.ok:
            if result.error == ErrorCodes.PERMISSION_DENIED:
                return Response({"detail": result.error_detail}, status=status.HTTP_403_FORBIDDEN)
            return Response({"detail": result.error_detail}, status=status.HTTP_400_BAD_REQUEST)

        return Response(self.get_serializer(result.value).data, status=status.HTTP_201_CREATED)

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

    @action(detail=False, methods=["get"])
    def my_products(self, request):
        """Get current user's products"""
        service = self.get_service()
        # Using list_products with seller filter
        result = service.list_products(filters={"seller": request.user.id})

        if not result.ok:
            return Response({"detail": result.error_detail}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        serializer = self.get_serializer(result.value["results"], many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def favorites(self, request):
        """Get user's favorite products"""
        if not request.user.is_authenticated:
            return Response({"detail": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)

        favorites = ProductFavorite.objects.filter(user=request.user).select_related("product")
        serializer = ProductFavoriteSerializer(favorites, many=True, context={"request": request})
        return Response(serializer.data)

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
