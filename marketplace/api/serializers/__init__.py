# Marketplace API Serializers

# Import response serializers for API documentation
from .response_serializers import (
    AddToCartRequestSerializer,
    AutocompleteResponseSerializer,
    CancelOrderRequestSerializer,
    CartResponseSerializer,
    CartValidationResponseSerializer,
    CreateOrderRequestSerializer,
    CreateReviewRequestSerializer,
    ErrorResponseSerializer,
    FiltersResponseSerializer,
    InternalOrderInfoSerializer,
    InternalProductInfoSerializer,
    OrderDetailResponseSerializer,
    OrderListResponseSerializer,
    ProductCreateRequestSerializer,
    ProductListResponseSerializer,
    RemoveFromCartRequestSerializer,
    ReturnRequestCreateSerializer,
    ReturnRequestSerializer,
    ReviewResponseSerializer,
    SellerProfileResponseSerializer,
    SuccessResponseSerializer,
    UpdateCartRequestSerializer,
)


__all__ = [
    # Response serializers for documentation
    "ErrorResponseSerializer",
    "SuccessResponseSerializer",
    "ProductListResponseSerializer",
    "ProductCreateRequestSerializer",
    "AddToCartRequestSerializer",
    "UpdateCartRequestSerializer",
    "RemoveFromCartRequestSerializer",
    "CartResponseSerializer",
    "CartValidationResponseSerializer",
    "CreateOrderRequestSerializer",
    "OrderDetailResponseSerializer",
    "OrderListResponseSerializer",
    "CancelOrderRequestSerializer",
    "ReturnRequestCreateSerializer",  # Added
    "ReturnRequestSerializer",  # Added
    "CreateReviewRequestSerializer",
    "ReviewResponseSerializer",
    "AutocompleteResponseSerializer",
    "FiltersResponseSerializer",
    "SellerProfileResponseSerializer",
    "InternalProductInfoSerializer",
    "InternalOrderInfoSerializer",
]
