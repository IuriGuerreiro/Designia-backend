from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response

from infrastructure.container import container
from marketplace.api.serializers import (
    CreateReviewRequestSerializer,
    ErrorResponseSerializer,
    ReviewResponseSerializer,
)
from marketplace.models import Product
from marketplace.serializers import ProductReviewSerializer
from marketplace.services import ErrorCodes, ReviewService


class ReviewViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_service(self) -> ReviewService:
        return container.review_service()

    def get_permissions(self):
        if self.action in ["create", "update", "destroy", "mark_helpful"]:
            return [IsAuthenticated()]
        return super().get_permissions()

    @extend_schema(
        operation_id="reviews_list",
        summary="List product reviews",
        description="""
        **What it receives:**
        - `product_slug` or `product_id` (query param): Product to get reviews for
        - Pagination parameters (page, page_size)
        - Ordering parameter

        **What it returns:**
        - Paginated list of reviews for the product
        """,
        parameters=[
            OpenApiParameter(name="product_slug", type=str, description="Product slug"),
            OpenApiParameter(name="product_id", type=str, description="Product UUID"),
            OpenApiParameter(name="page", type=int, description="Page number (default: 1)"),
            OpenApiParameter(name="page_size", type=int, description="Items per page (default: 20)"),
            OpenApiParameter(name="ordering", type=str, description="Order by field (default: -created_at)"),
        ],
        responses={
            200: OpenApiResponse(description="Reviews retrieved successfully"),
            400: OpenApiResponse(response=ErrorResponseSerializer, description="Missing product identifier"),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="Product not found"),
        },
        tags=["Marketplace - Reviews"],
    )
    def list(self, request, product_slug=None):
        service = self.get_service()

        # Product slug or ID handling
        # Priority: URL kwarg > query param
        product_slug = product_slug or self.kwargs.get("product_slug") or request.query_params.get("product_slug")
        product_id = request.query_params.get("product_id")

        if not product_id and product_slug:
            try:
                product = Product.objects.get(slug=product_slug)
                product_id = str(product.id)
            except Product.DoesNotExist:
                return Response({"detail": "Product not found"}, status=status.HTTP_404_NOT_FOUND)

        if not product_id:
            return Response({"detail": "product_id or product_slug is required"}, status=status.HTTP_400_BAD_REQUEST)

        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 20))
        sort_by = request.query_params.get("ordering", "-created_at")

        result = service.list_reviews(product_id, page, page_size, sort_by)

        if not result.ok:
            if result.error == ErrorCodes.PRODUCT_NOT_FOUND:
                return Response({"detail": result.error_detail}, status=status.HTTP_404_NOT_FOUND)
            return Response({"detail": result.error_detail}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Serialize results
        reviews_data = ProductReviewSerializer(result.value["results"], many=True).data
        response_data = result.value
        response_data["results"] = reviews_data

        return Response(response_data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="reviews_retrieve",
        summary="Get review details",
        responses={200: ReviewResponseSerializer, 404: ErrorResponseSerializer},
        tags=["Marketplace - Reviews"],
    )
    def retrieve(self, request, pk=None):
        """Get a specific review by ID."""
        service = self.get_service()

        result = service.get_review(pk)

        if not result.ok:
            if result.error == ErrorCodes.NOT_FOUND:
                return Response({"detail": result.error_detail}, status=status.HTTP_404_NOT_FOUND)
            return Response({"detail": result.error_detail}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(ProductReviewSerializer(result.value).data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="reviews_create",
        summary="Create product review",
        request=CreateReviewRequestSerializer,
        responses={201: ReviewResponseSerializer, 400: ErrorResponseSerializer, 404: ErrorResponseSerializer},
        tags=["Marketplace - Reviews"],
    )
    def create(self, request, product_slug=None):
        service = self.get_service()

        # Product slug or ID handling
        # Priority: URL kwarg > request data
        product_slug = product_slug or self.kwargs.get("product_slug") or request.data.get("product_slug")
        product_id = request.data.get("product_id")

        if not product_id and product_slug:
            try:
                product = Product.objects.get(slug=product_slug)
                product_id = str(product.id)
            except Product.DoesNotExist:
                return Response({"detail": "Product not found"}, status=status.HTTP_404_NOT_FOUND)

        if not product_id:
            return Response({"detail": "product_id or product_slug is required"}, status=status.HTTP_400_BAD_REQUEST)

        rating = request.data.get("rating")
        title = request.data.get("title", "")
        comment = request.data.get("comment", "")

        try:
            rating = int(rating)
        except (TypeError, ValueError):
            return Response({"detail": "Rating must be a number"}, status=status.HTTP_400_BAD_REQUEST)

        result = service.create_review(request.user, product_id, rating, title, comment)

        if not result.ok:
            if result.error == ErrorCodes.PRODUCT_NOT_FOUND:
                return Response({"detail": result.error_detail}, status=status.HTTP_404_NOT_FOUND)
            elif result.error == ErrorCodes.DUPLICATE_REVIEW:
                return Response({"detail": result.error_detail}, status=status.HTTP_400_BAD_REQUEST)
            elif result.error == ErrorCodes.PERMISSION_DENIED:
                return Response({"detail": result.error_detail}, status=status.HTTP_403_FORBIDDEN)
            elif result.error == ErrorCodes.INVALID_INPUT:
                return Response({"detail": result.error_detail}, status=status.HTTP_400_BAD_REQUEST)
            return Response({"detail": result.error_detail}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(ProductReviewSerializer(result.value).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        operation_id="reviews_update",
        summary="Update review",
        responses={200: ReviewResponseSerializer, 403: ErrorResponseSerializer, 404: ErrorResponseSerializer},
        tags=["Marketplace - Reviews"],
    )
    def update(self, request, pk=None):
        service = self.get_service()

        rating = request.data.get("rating")
        title = request.data.get("title")
        comment = request.data.get("comment")

        if rating is not None:
            try:
                rating = int(rating)
            except (TypeError, ValueError):
                return Response({"detail": "Rating must be a number"}, status=status.HTTP_400_BAD_REQUEST)

        result = service.update_review(request.user, pk, rating, title, comment)

        if not result.ok:
            if result.error == ErrorCodes.NOT_FOUND:
                return Response({"detail": result.error_detail}, status=status.HTTP_404_NOT_FOUND)
            elif result.error == ErrorCodes.PERMISSION_DENIED:
                return Response({"detail": result.error_detail}, status=status.HTTP_403_FORBIDDEN)
            elif result.error == ErrorCodes.INVALID_INPUT:
                return Response({"detail": result.error_detail}, status=status.HTTP_400_BAD_REQUEST)
            return Response({"detail": result.error_detail}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(ProductReviewSerializer(result.value).data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="reviews_partial_update",
        summary="Partially update review",
        responses={200: ReviewResponseSerializer, 403: ErrorResponseSerializer, 404: ErrorResponseSerializer},
        tags=["Marketplace - Reviews"],
    )
    def partial_update(self, request, pk=None):
        return self.update(request, pk)

    @extend_schema(
        operation_id="reviews_delete",
        summary="Delete review",
        responses={204: None, 403: ErrorResponseSerializer, 404: ErrorResponseSerializer},
        tags=["Marketplace - Reviews"],
    )
    def destroy(self, request, pk=None):
        service = self.get_service()

        result = service.delete_review(request.user, pk)

        if not result.ok:
            if result.error == ErrorCodes.NOT_FOUND:
                return Response({"detail": result.error_detail}, status=status.HTTP_404_NOT_FOUND)
            elif result.error == ErrorCodes.PERMISSION_DENIED:
                return Response({"detail": result.error_detail}, status=status.HTTP_403_FORBIDDEN)
            return Response({"detail": result.error_detail}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        operation_id="reviews_mark_helpful",
        summary="Mark review as helpful",
        responses={200: None, 403: ErrorResponseSerializer, 404: ErrorResponseSerializer},
        tags=["Marketplace - Reviews"],
    )
    @action(detail=True, methods=["post"])
    def mark_helpful(self, request, pk=None):
        service = self.get_service()

        result = service.mark_helpful(request.user, pk)

        if not result.ok:
            if result.error == ErrorCodes.NOT_FOUND:
                return Response({"detail": result.error_detail}, status=status.HTTP_404_NOT_FOUND)
            elif result.error == ErrorCodes.PERMISSION_DENIED:
                return Response({"detail": result.error_detail}, status=status.HTTP_403_FORBIDDEN)
            return Response({"detail": result.error_detail}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(result.value, status=status.HTTP_200_OK)
