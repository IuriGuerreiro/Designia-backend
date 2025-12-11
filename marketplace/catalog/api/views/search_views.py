from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from infrastructure.container import container
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

    @action(detail=False, methods=["get"])
    def search(self, request):
        service = self.get_service()

        query = request.query_params.get("q", "")

        # Extract filters
        filters = {}
        if request.query_params.get("category"):
            filters["category"] = request.query_params.get("category")
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
        if request.query_params.get("category"):
            filters["category"] = request.query_params.get("category")
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
