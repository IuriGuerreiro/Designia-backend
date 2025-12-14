from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from infrastructure.container import container
from marketplace.api.serializers import ErrorResponseSerializer
from marketplace.serializers import ProductListSerializer
from marketplace.services import SearchService


class SearchViewSet(viewsets.ViewSet):
    """
    ViewSet for search, filter, and autocomplete operations.
    Delegates logic to SearchService.
    """

    permission_classes = [AllowAny]

    def get_service(self) -> SearchService:
        return container.search_service()

    @extend_schema(
        operation_id="products_search",
        summary="Search products",
        description="Search for products with filters and pagination",
        parameters=[
            OpenApiParameter(name="q", type=str, description="Search query"),
            OpenApiParameter(name="category", type=str, description="Filter by category (can be multiple)", many=True),
            OpenApiParameter(
                name="condition", type=str, description="Filter by condition (can be multiple)", many=True
            ),
            OpenApiParameter(name="price_min", type=float, description="Minimum price"),
            OpenApiParameter(name="price_max", type=float, description="Maximum price"),
            OpenApiParameter(name="seller", type=str, description="Filter by seller ID"),
            OpenApiParameter(name="min_rating", type=float, description="Minimum rating"),
            OpenApiParameter(name="in_stock", type=bool, description="Only show in-stock products"),
            OpenApiParameter(name="is_featured", type=bool, description="Only show featured products"),
            OpenApiParameter(name="brand", type=str, description="Filter by brand"),
            OpenApiParameter(name="page", type=int, description="Page number (default: 1)"),
            OpenApiParameter(name="page_size", type=int, description="Items per page (default: 20)"),
            OpenApiParameter(name="sort", type=str, description="Sort by (relevance, price, newest, popular)"),
        ],
        responses={
            200: OpenApiResponse(
                response=inline_serializer(
                    name="ProductSearchPaginatedResponse",
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
                description="Search results",
            ),
            500: OpenApiResponse(response=ErrorResponseSerializer, description="Internal server error"),
        },
        tags=["Marketplace - Search"],
    )
    @action(detail=False, methods=["get"])
    def search(self, request):
        service = self.get_service()

        query = request.query_params.get("q", "")

        # Extract filters
        filters = {}
        categories = request.query_params.getlist("category")
        if categories:
            filters["category"] = categories

        conditions = request.query_params.getlist("condition")
        if conditions:
            filters["condition"] = conditions

        if request.query_params.get("price_min"):
            filters["price_min"] = request.query_params.get("price_min")
        if request.query_params.get("price_max"):
            filters["price_max"] = request.query_params.get("price_max")
        if request.query_params.get("seller"):
            filters["seller"] = request.query_params.get("seller")
        if request.query_params.get("min_rating"):
            filters["min_rating"] = request.query_params.get("min_rating")
        if request.query_params.get("in_stock"):
            filters["in_stock"] = request.query_params.get("in_stock").lower() == "true"
        if request.query_params.get("is_featured"):
            filters["is_featured"] = request.query_params.get("is_featured").lower() == "true"
        if request.query_params.get("brand"):
            filters["brand"] = request.query_params.get("brand")

        # Pagination and sorting
        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 20))
        sort = request.query_params.get("sort", "relevance")

        result = service.search(query, filters, sort, page, page_size)

        if not result.ok:
            return Response({"detail": result.error_detail}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Serialize products
        products_data = ProductListSerializer(result.value["results"], many=True, context={"request": request}).data
        response_data = result.value
        response_data["results"] = products_data

        return Response(response_data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"])
    def autocomplete(self, request):
        service = self.get_service()
        query = request.query_params.get("q", "")
        limit = int(request.query_params.get("limit", 10))

        result = service.autocomplete(query, limit)

        if not result.ok:
            return Response({"detail": result.error_detail}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(result.value, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"])
    def filters(self, request):
        service = self.get_service()

        # This endpoint is usually for fetching available filter options (facets)
        # or filtering without a search query (which search service supports via filter_products)

        # For now, let's use it as a direct interface to filter_products if no query is present
        # If it's meant to return available facets, that would require a new service method.
        # Based on "Filters: search_service.filter_products(filters) -> return filtered products" in AC

        # Extract filters (same as search)
        filters = {}
        categories = request.query_params.getlist("category")
        if categories:
            filters["category"] = categories

        conditions = request.query_params.getlist("condition")
        if conditions:
            filters["condition"] = conditions

        if request.query_params.get("price_min"):
            filters["price_min"] = request.query_params.get("price_min")
        if request.query_params.get("price_max"):
            filters["price_max"] = request.query_params.get("price_max")
        if request.query_params.get("seller"):
            filters["seller"] = request.query_params.get("seller")
        if request.query_params.get("min_rating"):
            filters["min_rating"] = request.query_params.get("min_rating")
        if request.query_params.get("in_stock"):
            filters["in_stock"] = request.query_params.get("in_stock").lower() == "true"
        if request.query_params.get("is_featured"):
            filters["is_featured"] = request.query_params.get("is_featured").lower() == "true"
        if request.query_params.get("brand"):
            filters["brand"] = request.query_params.get("brand")
        if request.query_params.get("condition"):
            filters["condition"] = request.query_params.get("condition")

        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 20))
        sort = request.query_params.get("sort", "newest")

        result = service.filter_products(filters, page, page_size, sort)

        if not result.ok:
            return Response({"detail": result.error_detail}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        products_data = ProductListSerializer(result.value["results"], many=True, context={"request": request}).data
        response_data = result.value
        response_data["results"] = products_data

        return Response(response_data, status=status.HTTP_200_OK)
