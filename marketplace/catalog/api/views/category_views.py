import logging

from django.db import models
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from activity.models import UserClick
from infrastructure.container import container
from marketplace.catalog.api.serializers.category_serializers import CategorySerializer
from marketplace.catalog.api.serializers.product_serializers import ProductListSerializer
from marketplace.catalog.domain.models.catalog import Product
from marketplace.filters import ProductFilter
from marketplace.services import CatalogService


logger = logging.getLogger(__name__)


@extend_schema_view(
    list=extend_schema(
        summary="List all categories",
        description="Retrieve a list of all active product categories.",
        responses={200: CategorySerializer(many=True)},
    ),
    retrieve=extend_schema(
        summary="Get category details",
        description="Retrieve details of a specific category by slug.",
        responses={200: CategorySerializer},
    ),
)
class CategoryViewSet(viewsets.ViewSet):
    """
    ViewSet for categories - read-only operations using Service Layer
    """

    permission_classes = [AllowAny]
    lookup_field = "slug"

    def get_service(self) -> CatalogService:
        return container.catalog_service()

    def list(self, request):
        service = self.get_service()
        result = service.list_categories(active_only=True)

        if not result.ok:
            return Response({"detail": result.error_detail}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        serializer = CategorySerializer(result.value, many=True)
        return Response(serializer.data)

    def retrieve(self, request, slug=None):
        service = self.get_service()
        result = service.get_category(slug)

        if not result.ok:
            if result.error == "NOT_FOUND":  # Assuming ErrorCodes.NOT_FOUND maps to this string or similar
                return Response({"detail": result.error_detail}, status=status.HTTP_404_NOT_FOUND)
            return Response({"detail": result.error_detail}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        serializer = CategorySerializer(result.value)
        return Response(serializer.data)

    @extend_schema(
        summary="Get products from category",
        description="Retrieve a list of products within the specified category.",
        responses={200: ProductListSerializer(many=True)},
    )
    @action(detail=True, methods=["get"])
    def products(self, request, slug=None):
        """Get products in this category with view tracking"""
        # This method mixes service/ORM. For now, keep as is but fetch category via service?
        # Or keep using get_object() logic manually?

        service = self.get_service()
        cat_result = service.get_category(slug)
        if not cat_result.ok:
            return Response({"detail": "Category not found"}, status=status.HTTP_404_NOT_FOUND)

        category = cat_result.value

        products = (
            Product.objects.filter(category=category, is_active=True)
            .select_related("seller", "category")
            .prefetch_related("images", "reviews__reviewer", "favorited_by")
            .annotate(
                calculated_review_count=models.Count("reviews", filter=models.Q(reviews__is_active=True)),
                calculated_avg_rating=models.Avg("reviews__rating", filter=models.Q(reviews__is_active=True)),
            )
        )

        # Apply filtering
        filter_backend = ProductFilter()
        products = filter_backend.filter_queryset(request, products, self)

        # Track category views
        try:
            from marketplace.tracking_utils import MetricsHelper, SessionHelper

            user, session_key = SessionHelper.get_user_or_session(request)
            products_list = list(products)

            if products_list:
                MetricsHelper.bulk_ensure_metrics(products_list)

                for product in products_list:
                    try:
                        UserClick.track_activity(
                            product=product,
                            action="category_view",
                            user=user,
                            session_key=session_key,
                            request=request,
                        )
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"Error tracking category listing views: {str(e)}")

        serializer = ProductListSerializer(products, many=True, context={"request": request})
        return Response(serializer.data)
