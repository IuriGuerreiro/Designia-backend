from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated

from marketplace.models import Product, ProductImage
from marketplace.permissions import IsOwnerOrReadOnly
from marketplace.serializers import ProductImageSerializer


class ProductImageViewSet(viewsets.ModelViewSet):
    """
    ViewSet for product images
    """

    serializer_class = ProductImageSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrReadOnly]

    def get_queryset(self):
        product_slug = self.kwargs.get("product_slug")
        if product_slug:
            return ProductImage.objects.filter(product__slug=product_slug)
        return ProductImage.objects.none()

    def perform_create(self, serializer):
        product_slug = self.kwargs.get("product_slug")
        product = get_object_or_404(Product, slug=product_slug)

        # Check if user owns the product
        if product.seller != self.request.user:
            raise PermissionDenied("You can only add images to your own products")

        serializer.save(product=product)
