from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from marketplace.models import ProductMetrics
from marketplace.permissions import IsSellerUser
from marketplace.serializers import ProductMetricsSerializer


class ProductMetricsViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for product metrics - read-only for sellers
    """

    serializer_class = ProductMetricsSerializer
    permission_classes = [IsAuthenticated, IsSellerUser]

    def get_queryset(self):
        # Only return metrics for products owned by the current user
        return ProductMetrics.objects.filter(product__seller=self.request.user)
