from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response

from infrastructure.container import container
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

    def list(self, request):
        service = self.get_service()

        # Product slug or ID handling
        product_slug = request.query_params.get("product_slug")
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

    def retrieve(self, request, pk=None):
        """Get a specific review by ID."""
        service = self.get_service()

        result = service.get_review(pk)

        if not result.ok:
            if result.error == ErrorCodes.NOT_FOUND:
                return Response({"detail": result.error_detail}, status=status.HTTP_404_NOT_FOUND)
            return Response({"detail": result.error_detail}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(ProductReviewSerializer(result.value).data, status=status.HTTP_200_OK)

    def create(self, request):
        service = self.get_service()

        product_slug = request.data.get("product_slug")
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
            elif result.error == ErrorCodes.INVALID_INPUT:
                return Response({"detail": result.error_detail}, status=status.HTTP_400_BAD_REQUEST)
            return Response({"detail": result.error_detail}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(ProductReviewSerializer(result.value).data, status=status.HTTP_201_CREATED)

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

    def partial_update(self, request, pk=None):
        return self.update(request, pk)

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
