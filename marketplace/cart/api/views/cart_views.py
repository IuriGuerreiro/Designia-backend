# Designia-backend/marketplace/views/cart_views.py
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from infrastructure.container import container  # For DI
from marketplace.api.serializers import (
    AddToCartRequestSerializer,
    CartResponseSerializer,
    ErrorResponseSerializer,
    RemoveFromCartRequestSerializer,
    UpdateCartRequestSerializer,
)
from marketplace.serializers import (  # Use CartItemSerializer for input validation
    CartItemSerializer,
    CartServiceOutputSerializer,
)
from marketplace.services import CartService, ErrorCodes  # Import the service and error codes


class CartViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def get_service(self) -> CartService:
        # Inject CartService via DI container
        return container.cart_service()

    def get_serializer(self, *args, **kwargs):
        # A serializer for cart input (e.g., adding items)
        return CartItemSerializer(*args, **kwargs)

    def get_output_serializer(self, *args, **kwargs):
        # A serializer for cart output
        return CartServiceOutputSerializer(*args, **kwargs)

    @extend_schema(
        operation_id="cart_get",
        summary="Get user's shopping cart",
        description="""
        **What it receives:**
        - Authentication token (header)

        **What it returns:**
        - Cart items with product details
        - Totals (subtotal, shipping, tax, total)
        - Item count
        """,
        responses={
            200: OpenApiResponse(response=CartResponseSerializer, description="Cart retrieved successfully"),
            500: OpenApiResponse(response=ErrorResponseSerializer, description="Internal server error"),
        },
        tags=["Marketplace - Cart"],
    )
    def list(self, request):
        service = self.get_service()
        result = service.get_cart(request.user)

        if not result.ok:
            return Response({"detail": result.error_detail}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Serialize the service output dictionary
        output_data = self.get_output_serializer(result.value).data
        return Response(output_data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="cart_add_item",
        summary="Add item to cart",
        description="""
        **What it receives:**
        - `product_id` (UUID): Product to add
        - `quantity` (integer, optional): Quantity to add (default: 1)

        **What it returns:**
        - Updated cart with all items
        - Updated totals
        """,
        request=AddToCartRequestSerializer,
        responses={
            200: OpenApiResponse(response=CartResponseSerializer, description="Item added successfully"),
            400: OpenApiResponse(response=ErrorResponseSerializer, description="Invalid data or insufficient stock"),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="Product not found"),
            500: OpenApiResponse(response=ErrorResponseSerializer, description="Internal server error"),
        },
        tags=["Marketplace - Cart"],
    )
    @action(detail=False, methods=["post"])
    def add_item(self, request):
        service = self.get_service()
        # Use CartItemSerializer for input validation
        input_serializer = self.get_serializer(data=request.data)
        if not input_serializer.is_valid():
            return Response(input_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        product_id = input_serializer.validated_data.get("product_id")
        quantity = input_serializer.validated_data.get("quantity", 1)

        result = service.add_to_cart(request.user, product_id, quantity)

        if not result.ok:
            if result.error == ErrorCodes.PRODUCT_NOT_FOUND:
                return Response({"detail": result.error_detail}, status=status.HTTP_404_NOT_FOUND)
            elif result.error == ErrorCodes.INSUFFICIENT_STOCK:
                return Response({"detail": result.error_detail}, status=status.HTTP_400_BAD_REQUEST)
            elif result.error == ErrorCodes.INVALID_QUANTITY:
                return Response({"detail": result.error_detail}, status=status.HTTP_400_BAD_REQUEST)
            return Response({"detail": result.error_detail}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Service returns full cart data
        output_data = self.get_output_serializer(result.value).data
        return Response(output_data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="cart_update_item",
        summary="Update item quantity in cart",
        description="""
        **What it receives:**
        - `product_id` (UUID): Product to update
        - `quantity` (integer): New quantity (0 to remove item)

        **What it returns:**
        - Updated cart with modified quantities
        - Updated totals
        """,
        request=UpdateCartRequestSerializer,
        responses={
            200: OpenApiResponse(response=CartResponseSerializer, description="Item updated successfully"),
            400: OpenApiResponse(response=ErrorResponseSerializer, description="Invalid data or insufficient stock"),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="Item not in cart"),
            500: OpenApiResponse(response=ErrorResponseSerializer, description="Internal server error"),
        },
        tags=["Marketplace - Cart"],
    )
    @action(detail=False, methods=["patch"])
    def update_item(self, request):
        service = self.get_service()
        # For update, we expect product_id and quantity directly from request.data
        product_id = request.data.get("product_id")
        quantity = request.data.get("quantity")

        if not product_id or quantity is None:
            return Response({"detail": "product_id and quantity are required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            quantity = int(quantity)
        except (ValueError, TypeError):
            return Response({"detail": "Quantity must be a valid number"}, status=status.HTTP_400_BAD_REQUEST)

        result = service.update_quantity(request.user, product_id, quantity)

        if not result.ok:
            if result.error == ErrorCodes.ITEM_NOT_IN_CART:
                return Response({"detail": result.error_detail}, status=status.HTTP_404_NOT_FOUND)
            elif result.error == ErrorCodes.INSUFFICIENT_STOCK:
                return Response({"detail": result.error_detail}, status=status.HTTP_400_BAD_REQUEST)
            elif result.error == ErrorCodes.INVALID_QUANTITY:
                return Response({"detail": result.error_detail}, status=status.HTTP_400_BAD_REQUEST)
            return Response({"detail": result.error_detail}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        output_data = self.get_output_serializer(result.value).data
        return Response(output_data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="cart_remove_item",
        summary="Remove item from cart",
        description="""
        **What it receives:**
        - `product_id` (UUID): Product to remove

        **What it returns:**
        - Updated cart without the removed item
        - Updated totals
        """,
        request=RemoveFromCartRequestSerializer,
        responses={
            200: OpenApiResponse(response=CartResponseSerializer, description="Item removed successfully"),
            400: OpenApiResponse(response=ErrorResponseSerializer, description="Invalid product_id"),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="Item not in cart"),
            500: OpenApiResponse(response=ErrorResponseSerializer, description="Internal server error"),
        },
        tags=["Marketplace - Cart"],
    )
    @action(detail=False, methods=["delete"])
    def remove_item(self, request):
        service = self.get_service()
        product_id = request.data.get("product_id")

        if not product_id:
            return Response({"detail": "product_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        result = service.remove_from_cart(request.user, product_id)

        if not result.ok:
            if result.error == ErrorCodes.ITEM_NOT_IN_CART:
                return Response({"detail": result.error_detail}, status=status.HTTP_404_NOT_FOUND)
            return Response({"detail": result.error_detail}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        output_data = self.get_output_serializer(result.value).data
        return Response(output_data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="cart_clear",
        summary="Clear all items from cart",
        description="""
        **What it receives:**
        - Authentication token (header)

        **What it returns:**
        - Success message (204 No Content)
        """,
        responses={
            204: OpenApiResponse(description="Cart cleared successfully"),
            500: OpenApiResponse(response=ErrorResponseSerializer, description="Internal server error"),
        },
        tags=["Marketplace - Cart"],
    )
    @action(detail=False, methods=["delete"])
    def clear(self, request):
        service = self.get_service()
        result = service.clear_cart(request.user)

        if not result.ok:
            return Response({"detail": result.error_detail}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"detail": "Cart cleared successfully"}, status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        operation_id="cart_status",
        summary="Get cart status summary",
        description="""
        **What it receives:**
        - Authentication token (header)

        **What it returns:**
        - Cart ID
        - Total items count
        - Total amount
        - Modifiable status
        - Last updated timestamp
        """,
        responses={
            200: OpenApiResponse(description="Cart status retrieved successfully"),
            500: OpenApiResponse(response=ErrorResponseSerializer, description="Internal server error"),
        },
        tags=["Marketplace - Cart"],
    )
    @action(detail=False, methods=["get"])
    def status(self, request):
        service = self.get_service()
        result = service.get_cart(request.user)

        if not result.ok:
            return Response({"detail": result.error_detail}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        cart_data = result.value
        # Extract fields needed for lightweight status
        status_data = {
            "id": str(cart_data["id"]),
            "total_items": cart_data["items_count"],
            "total_amount": str(cart_data["totals"].get("total", "0.00")),
            "can_modify": True,
            "is_locked": False,
            "updated_at": cart_data["updated_at"],
        }
        return Response(status_data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="cart_validate_stock",
        summary="Validate cart items stock availability",
        description="""
        **What it receives:**
        - Authentication token (header)

        **What it returns:**
        - Validation result (valid: boolean)
        - List of issues (out_of_stock, inactive, price_changed)
        """,
        responses={
            200: OpenApiResponse(description="Validation completed"),
            500: OpenApiResponse(response=ErrorResponseSerializer, description="Internal server error"),
        },
        tags=["Marketplace - Cart"],
    )
    @action(detail=False, methods=["post"])
    def validate_stock(self, request):
        service = self.get_service()
        result = service.validate_cart(request.user)

        if not result.ok:
            return Response({"detail": result.error_detail}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(result.value, status=status.HTTP_200_OK)
