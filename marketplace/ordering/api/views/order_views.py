from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from infrastructure.container import container
from marketplace.api.serializers import (
    CancelOrderRequestSerializer,
    CreateOrderRequestSerializer,
    ErrorResponseSerializer,
    OrderDetailResponseSerializer,
    OrderListResponseSerializer,
    ReturnRequestCreateSerializer,  # NEW
    ReturnRequestSerializer,  # NEW
)
from marketplace.serializers import OrderSerializer
from marketplace.services import ErrorCodes, OrderService


class OrderViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def get_service(self) -> OrderService:
        return container.order_service()

    @extend_schema(
        operation_id="orders_list",
        summary="List user's orders (as buyer)",
        description="""
        **What it receives:**
        - Authentication token
        - Optional status filter (query param)
        - Pagination parameters (page, page_size)

        **What it returns:**
        - Paginated list of orders where user is the buyer
        - Total count and page information
        """,
        parameters=[
            OpenApiParameter(name="status", type=str, description="Filter by order status"),
            OpenApiParameter(name="page", type=int, description="Page number (default: 1)"),
            OpenApiParameter(name="page_size", type=int, description="Items per page (default: 20)"),
        ],
        responses={
            200: OpenApiResponse(response=OrderListResponseSerializer, description="Orders retrieved successfully"),
            500: OpenApiResponse(response=ErrorResponseSerializer, description="Internal server error"),
        },
        tags=["Marketplace - Orders"],
    )
    def list(self, request):
        service = self.get_service()

        status_filter = request.query_params.get("status")
        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 20))

        result = service.list_orders(request.user, status_filter, page, page_size)

        if not result.ok:
            return Response({"detail": result.error_detail}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Serialize results
        orders_data = OrderSerializer(result.value["results"], many=True).data
        response_data = result.value
        response_data["results"] = orders_data

        return Response(response_data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="orders_seller_orders",
        summary="List orders where user is the seller",
        description="""
        **What it receives:**
        - Authentication token (user must have products as seller)
        - Optional status filter (query param)
        - Pagination parameters (page, page_size)

        **What it returns:**
        - Paginated list of orders containing items sold by current user
        - Total count and page information
        """,
        parameters=[
            OpenApiParameter(name="status", type=str, description="Filter by order status"),
            OpenApiParameter(name="page", type=int, description="Page number (default: 1)"),
            OpenApiParameter(name="page_size", type=int, description="Items per page (default: 20)"),
        ],
        responses={
            200: OpenApiResponse(response=OrderListResponseSerializer, description="Orders retrieved successfully"),
            500: OpenApiResponse(response=ErrorResponseSerializer, description="Internal server error"),
        },
        tags=["Marketplace - Orders"],
    )
    @action(detail=False, methods=["get"])
    def seller_orders(self, request):
        service = self.get_service()

        status_filter = request.query_params.get("status")
        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 20))

        result = service.list_seller_orders(request.user, status_filter, page, page_size)

        if not result.ok:
            return Response({"detail": result.error_detail}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Serialize results
        orders_data = OrderSerializer(result.value["results"], many=True).data
        response_data = result.value
        response_data["results"] = orders_data

        return Response(response_data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="orders_retrieve",
        summary="Get order details",
        description="""
        **What it receives:**
        - `order_id` (UUID in URL): Order to retrieve
        - Authentication token (must be order buyer or seller of items)

        **What it returns:**
        - Complete order details including items, shipping, payment status
        """,
        responses={
            200: OpenApiResponse(response=OrderDetailResponseSerializer, description="Order retrieved successfully"),
            403: OpenApiResponse(response=ErrorResponseSerializer, description="Not order owner"),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="Order not found"),
            500: OpenApiResponse(response=ErrorResponseSerializer, description="Internal server error"),
        },
        tags=["Marketplace - Orders"],
    )
    def retrieve(self, request, pk=None):
        service = self.get_service()

        result = service.get_order(pk, request.user)

        if not result.ok:
            if result.error == ErrorCodes.ORDER_NOT_FOUND:
                return Response({"detail": result.error_detail}, status=status.HTTP_404_NOT_FOUND)
            elif result.error == ErrorCodes.NOT_ORDER_OWNER:
                return Response({"detail": result.error_detail}, status=status.HTTP_403_FORBIDDEN)
            return Response({"detail": result.error_detail}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(OrderSerializer(result.value).data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="orders_create",
        summary="Create order from cart",
        description="""
        **What it receives:**
        - `shipping_address` (object): Delivery address (street, city, country required)
        - `buyer_notes` (string, optional): Notes for seller
        - `shipping_cost` (decimal, optional): Override shipping cost
        - Authentication token

        **What it returns:**
        - Created order with pending payment status
        - Cart is cleared after order creation
        - Stock is reserved for order items
        """,
        request=CreateOrderRequestSerializer,
        responses={
            201: OpenApiResponse(response=OrderDetailResponseSerializer, description="Order created successfully"),
            400: OpenApiResponse(response=ErrorResponseSerializer, description="Cart empty or validation error"),
            409: OpenApiResponse(
                response=ErrorResponseSerializer, description="Insufficient stock or reservation failed"
            ),
            500: OpenApiResponse(response=ErrorResponseSerializer, description="Internal server error"),
        },
        tags=["Marketplace - Orders"],
    )
    def create(self, request):
        service = self.get_service()

        # Assuming the request data contains shipping_address and buyer_notes
        shipping_address = request.data.get("shipping_address")
        buyer_notes = request.data.get("buyer_notes", "")
        shipping_cost = request.data.get("shipping_cost")  # Optional override

        if not shipping_address:
            return Response({"detail": "shipping_address is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Validate shipping address structure (basic check)
        required_address_fields = ["street", "city", "country"]
        if not all(field in shipping_address for field in required_address_fields):
            return Response(
                {"detail": f"shipping_address must contain: {', '.join(required_address_fields)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Optionally get cart_id if needed, but OrderService.create_order uses user's current cart
        # cart_id = request.data.get("cart_id")
        # For simplicity, we use the user's current active cart as per OrderService's create_order method

        result = service.create_order(request.user, shipping_address, buyer_notes, shipping_cost)

        if not result.ok:
            if result.error == ErrorCodes.CART_EMPTY:
                return Response({"detail": result.error_detail}, status=status.HTTP_400_BAD_REQUEST)
            elif result.error == ErrorCodes.VALIDATION_ERROR:
                return Response({"detail": result.error_detail}, status=status.HTTP_400_BAD_REQUEST)
            elif result.error == ErrorCodes.INSUFFICIENT_STOCK:  # From nested inventory service
                return Response({"detail": result.error_detail}, status=status.HTTP_409_CONFLICT)
            elif result.error == ErrorCodes.RESERVATION_FAILED:
                return Response({"detail": result.error_detail}, status=status.HTTP_409_CONFLICT)
            return Response({"detail": result.error_detail}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(OrderSerializer(result.value).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        operation_id="orders_update_shipping",
        summary="Update order shipping information (Seller/Admin only)",
        description="""
        **What it receives:**
        - `order_id` (UUID in URL): Order to update
        - `tracking_number` (string): Shipment tracking number
        - `shipping_carrier` (string): Carrier name (e.g., "UPS", "FedEx")
        - `carrier_code` (string, optional): Carrier code
        - Authentication token (must be seller of items in order or admin)

        **What it returns:**
        - Updated order with shipping information
        - Order status transitions to "shipped"
        """,
        responses={
            200: OpenApiResponse(response=OrderDetailResponseSerializer, description="Shipping updated successfully"),
            400: OpenApiResponse(
                response=ErrorResponseSerializer, description="Invalid order state or missing fields"
            ),
            403: OpenApiResponse(response=ErrorResponseSerializer, description="Permission denied"),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="Order not found"),
            500: OpenApiResponse(response=ErrorResponseSerializer, description="Internal server error"),
        },
        tags=["Marketplace - Orders"],
    )
    @action(detail=True, methods=["patch"])
    def update_shipping(self, request, pk=None):
        service = self.get_service()

        tracking_number = request.data.get("tracking_number")
        carrier = request.data.get("shipping_carrier")
        carrier_code = request.data.get("carrier_code", "")

        if not tracking_number or not carrier:
            return Response(
                {"detail": "tracking_number and shipping_carrier are required"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Assuming user must be staff or seller of items in order to update shipping
        # The service method handles the actual permission checking internally based on order items
        # if not request.user.is_staff and not order.items.filter(seller=request.user).exists():
        #     return Response({"detail": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)
        # OrderService.update_shipping does not take user param, so permission check needed here or ensure in service.

        # For this story, `update_shipping` is meant for admin/seller. Let's assume the service handles internal permission or a higher-level permission class.
        # But `OrderService.update_shipping` doesn't take `user`. So, a permission check on the Order items from the view might be needed before calling the service.
        # However, the AC says: "update_shipping()" is migrated. And service handles "state transitions".
        # Let's adjust for `update_shipping` to take a user, and service checks if user is seller of items.

        # For simplicity, for now, we'll let service handle internal state checks, but for permission
        # the view needs to check if current user has rights to update this order's shipping.
        # Given in `views_legacy.py` there was `if not (request.user == order.buyer or order.items.filter(seller=request.user).exists() or request.user.is_staff):`
        # Let's add that to the view before calling the service, or make service take user.
        # The service method `update_shipping` does NOT take user currently. It's more of a system-level update.
        # Let's assume for this story, `update_shipping` is for an admin or privileged user via another viewset.
        # Or, the AC says "Order list filtered by user (can't see others' orders)". So, it implies the viewset scope handles user.
        # But `update_shipping` is an action on `detail=True`.

        # Let's adjust the update_shipping in OrderService to take user to check permission properly.
        # But wait, it's about migrating existing endpoints. Let's assume for now, `update_shipping` is a system call.
        # Or I need to manually fetch the order here and verify permission before calling service.
        # AC: "Order list filtered by user (can't see others' orders)" means list/retrieve only for owner.
        # `update_shipping` in views_legacy was:
        # `if not (request.user == order.buyer or order.items.filter(seller=request.user).exists() or request.user.is_staff):`
        # This means anyone associated with the order (buyer, seller, admin) can update status.

        # For `update_shipping`, the `OrderService` method should ideally take `user` and perform authorization internally.
        # I need to modify `OrderService.update_shipping` to take `user`.

        result = service.update_shipping(pk, request.user, tracking_number, carrier, carrier_code)

        if not result.ok:
            if result.error == ErrorCodes.ORDER_NOT_FOUND:
                return Response({"detail": result.error_detail}, status=status.HTTP_404_NOT_FOUND)
            elif result.error == ErrorCodes.INVALID_ORDER_STATE:
                return Response({"detail": result.error_detail}, status=status.HTTP_400_BAD_REQUEST)
            elif result.error == ErrorCodes.PERMISSION_DENIED:
                return Response({"detail": result.error_detail}, status=status.HTTP_403_FORBIDDEN)
            return Response({"detail": result.error_detail}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(OrderSerializer(result.value).data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="orders_return_request",
        summary="Create return request for order",
        description="""
        **What it receives:**
        - `order_id` (UUID in URL): Order for which to request return
        - `items` (list of objects): Items to return with quantities (`itemId`, `quantity`)
        - `reason` (string): Reason for return
        - `comment` (string, optional): Additional comments
        - `proof_image_urls` (list of strings, optional): URLs of proof images
        - Authentication token (must be order buyer)

        **What it returns:**
        - Created return request
        - Order status transitions to "return_requested"
        """,
        request=ReturnRequestCreateSerializer,
        responses={
            201: OpenApiResponse(response=ReturnRequestSerializer, description="Return request created successfully"),
            400: OpenApiResponse(response=ErrorResponseSerializer, description="Invalid data or order state"),
            403: OpenApiResponse(response=ErrorResponseSerializer, description="Not order owner"),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="Order not found"),
            500: OpenApiResponse(response=ErrorResponseSerializer, description="Internal server error"),
        },
        tags=["Marketplace - Orders"],
    )
    @action(detail=True, methods=["post"], url_path="return")
    def return_request(self, request, pk=None):
        service = self.get_service()
        serializer = ReturnRequestCreateSerializer(data=request.data, context={"order_id": pk})
        serializer.is_valid(raise_exception=True)

        items_data = serializer.validated_data.get("items")  # Frontend sends itemId and quantity
        reason = serializer.validated_data.get("reason")
        comment = serializer.validated_data.get("comment")
        proof_image_urls = serializer.validated_data.get("proof_image_urls")

        result = service.create_return_request(
            order_id=pk,
            user=request.user,
            items_data=items_data,
            reason=reason,
            comment=comment,
            proof_image_urls=proof_image_urls,
        )

        if not result.ok:
            if result.error == ErrorCodes.ORDER_NOT_FOUND:
                return Response({"detail": result.error_detail}, status=status.HTTP_404_NOT_FOUND)
            elif result.error == ErrorCodes.NOT_ORDER_OWNER:
                return Response({"detail": result.error_detail}, status=status.HTTP_403_FORBIDDEN)
            elif result.error == ErrorCodes.INVALID_ORDER_STATE:
                return Response({"detail": result.error_detail}, status=status.HTTP_400_BAD_REQUEST)
            elif result.error == ErrorCodes.ITEM_NOT_FOUND:
                return Response({"detail": result.error_detail}, status=status.HTTP_400_BAD_REQUEST)
            elif result.error == ErrorCodes.INVALID_QUANTITY:
                return Response({"detail": result.error_detail}, status=status.HTTP_400_BAD_REQUEST)
            return Response({"detail": result.error_detail}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(ReturnRequestSerializer(result.value).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        operation_id="orders_cancel",
        summary="Cancel order",
        description="""
        **What it receives:**
        - `order_id` (UUID in URL): Order to cancel
        - `reason` (string, optional): Cancellation reason
        - Authentication token (must be order buyer)

        **What it returns:**
        - Updated order with cancelled status
        - Reserved stock is released back to inventory
        """,
        request=CancelOrderRequestSerializer,
        responses={
            200: OpenApiResponse(response=OrderDetailResponseSerializer, description="Order cancelled successfully"),
            400: OpenApiResponse(
                response=ErrorResponseSerializer, description="Order cannot be cancelled (already shipped/delivered)"
            ),
            403: OpenApiResponse(response=ErrorResponseSerializer, description="Not order owner"),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="Order not found"),
            500: OpenApiResponse(response=ErrorResponseSerializer, description="Internal server error"),
        },
        tags=["Marketplace - Orders"],
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        service = self.get_service()

        reason = request.data.get("reason", "")

        result = service.cancel_order(pk, request.user, reason)

        if not result.ok:
            if result.error == ErrorCodes.ORDER_NOT_FOUND:
                return Response({"detail": result.error_detail}, status=status.HTTP_404_NOT_FOUND)
            elif result.error == ErrorCodes.NOT_ORDER_OWNER:
                return Response({"detail": result.error_detail}, status=status.HTTP_403_FORBIDDEN)
            elif result.error == ErrorCodes.ORDER_CANNOT_CANCEL:
                return Response({"detail": result.error_detail}, status=status.HTTP_400_BAD_REQUEST)
            return Response({"detail": result.error_detail}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(OrderSerializer(result.value).data, status=status.HTTP_200_OK)
