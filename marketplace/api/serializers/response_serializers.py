"""
Response Serializers for Marketplace API Documentation

These serializers define the structure of API responses for OpenAPI schema generation.
They are NOT used for data validation, only for documentation in Swagger/ReDoc.
"""

from rest_framework import serializers

# ===== Common Response Serializers =====


class ErrorResponseSerializer(serializers.Serializer):
    """Standard error response"""

    error = serializers.CharField(help_text="Error code identifier")
    message = serializers.CharField(help_text="Human-readable error message")
    detail = serializers.CharField(help_text="Additional error details", required=False)


class SuccessResponseSerializer(serializers.Serializer):
    """Generic success response"""

    message = serializers.CharField(help_text="Success message")


# ===== Product Response Serializers =====


class ProductListResponseSerializer(serializers.Serializer):
    """Paginated product list response"""

    count = serializers.IntegerField(help_text="Total number of products")
    page = serializers.IntegerField(help_text="Current page number")
    page_size = serializers.IntegerField(help_text="Items per page")
    num_pages = serializers.IntegerField(help_text="Total number of pages")
    has_next = serializers.BooleanField(help_text="Whether there is a next page")
    has_previous = serializers.BooleanField(help_text="Whether there is a previous page")
    results = serializers.ListField(
        child=serializers.DictField(), help_text="List of products (see ProductListSerializer schema)"
    )


class ProductCreateRequestSerializer(serializers.Serializer):
    """Request body for creating a product"""

    name = serializers.CharField(max_length=255, help_text="Product name")
    description = serializers.CharField(help_text="Full product description", required=False)
    short_description = serializers.CharField(max_length=500, help_text="Brief description", required=False)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, help_text="Product price")
    original_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, help_text="Original price (for discount display)", required=False
    )
    category_id = serializers.IntegerField(help_text="Category ID")
    stock_quantity = serializers.IntegerField(min_value=0, help_text="Available stock quantity")
    condition = serializers.ChoiceField(
        choices=["new", "like_new", "used", "refurbished"], default="new", help_text="Product condition"
    )
    brand = serializers.CharField(max_length=100, help_text="Product brand", required=False)
    model = serializers.CharField(max_length=100, help_text="Product model", required=False)
    colors = serializers.ListField(child=serializers.CharField(), help_text="Available colors", required=False)
    materials = serializers.CharField(help_text="Materials used", required=False)
    tags = serializers.ListField(child=serializers.CharField(), help_text="Product tags", required=False)
    is_digital = serializers.BooleanField(default=False, help_text="Whether product is digital (no shipping)")


# ===== Cart Response Serializers =====


class AddToCartRequestSerializer(serializers.Serializer):
    """Request body for adding item to cart"""

    product_id = serializers.UUIDField(help_text="Product UUID to add")
    quantity = serializers.IntegerField(min_value=1, default=1, help_text="Quantity to add (default: 1)")


class UpdateCartRequestSerializer(serializers.Serializer):
    """Request body for updating cart item"""

    product_id = serializers.UUIDField(help_text="Product UUID to update")
    quantity = serializers.IntegerField(min_value=0, help_text="New quantity (0 to remove item)")


class RemoveFromCartRequestSerializer(serializers.Serializer):
    """Request body for removing item from cart"""

    product_id = serializers.UUIDField(help_text="Product UUID to remove")


class CartItemSerializer(serializers.Serializer):
    """Single cart item"""

    product = serializers.DictField(help_text="Product details (see ProductListSerializer)")
    quantity = serializers.IntegerField(help_text="Quantity in cart")
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, help_text="Item subtotal (price × quantity)")


class CartTotalsSerializer(serializers.Serializer):
    """Cart totals breakdown"""

    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, help_text="Sum of all items")
    shipping = serializers.DecimalField(max_digits=10, decimal_places=2, help_text="Estimated shipping cost")
    tax = serializers.DecimalField(max_digits=10, decimal_places=2, help_text="Estimated tax")
    total = serializers.DecimalField(max_digits=10, decimal_places=2, help_text="Final total amount")


class CartResponseSerializer(serializers.Serializer):
    """Complete cart response"""

    items = serializers.ListField(child=CartItemSerializer(), help_text="Cart items")
    totals = CartTotalsSerializer(help_text="Cart totals")
    item_count = serializers.IntegerField(help_text="Total number of items")


class CartValidationIssueSerializer(serializers.Serializer):
    """Single cart validation issue"""

    product_id = serializers.UUIDField(help_text="Product with issue")
    issue_type = serializers.ChoiceField(
        choices=["out_of_stock", "inactive", "price_changed"], help_text="Type of issue"
    )
    message = serializers.CharField(help_text="Description of the issue")


class CartValidationResponseSerializer(serializers.Serializer):
    """Cart validation result"""

    valid = serializers.BooleanField(help_text="Whether cart is valid for checkout")
    issues = serializers.ListField(child=CartValidationIssueSerializer(), help_text="List of validation issues")


# ===== Order Response Serializers =====


class ShippingAddressSerializer(serializers.Serializer):
    """Shipping address structure"""

    street = serializers.CharField(help_text="Street address")
    city = serializers.CharField(help_text="City")
    state = serializers.CharField(help_text="State/Province")
    postal_code = serializers.CharField(help_text="Postal/ZIP code")
    country = serializers.CharField(help_text="Country")


class CreateOrderRequestSerializer(serializers.Serializer):
    """Request body for creating an order"""

    shipping_address = ShippingAddressSerializer(help_text="Delivery address")
    buyer_notes = serializers.CharField(
        help_text="Optional notes for seller (e.g., delivery instructions)", required=False
    )


class OrderItemSerializer(serializers.Serializer):
    """Single order item"""

    id = serializers.IntegerField(help_text="Order item ID")
    product = serializers.DictField(help_text="Product snapshot at time of order")
    quantity = serializers.IntegerField(help_text="Quantity ordered")
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, help_text="Price per unit at time of order")
    total_price = serializers.DecimalField(max_digits=10, decimal_places=2, help_text="Total for this item")
    product_name = serializers.CharField(help_text="Product name (snapshot)")
    product_image = serializers.URLField(help_text="Product image URL (snapshot)")


class OrderListItemSerializer(serializers.Serializer):
    """Order in list view (summary)"""

    id = serializers.UUIDField(help_text="Order UUID")
    status = serializers.ChoiceField(
        choices=[
            "pending_payment",
            "payment_confirmed",
            "awaiting_shipment",
            "shipped",
            "delivered",
            "cancelled",
            "refunded",
        ],
        help_text="Order status",
    )
    payment_status = serializers.ChoiceField(
        choices=["pending", "paid", "failed", "refunded"], help_text="Payment status"
    )
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2, help_text="Order total")
    created_at = serializers.DateTimeField(help_text="Order creation timestamp")
    item_count = serializers.IntegerField(help_text="Number of items in order")


class OrderDetailResponseSerializer(serializers.Serializer):
    """Detailed order response"""

    id = serializers.UUIDField(help_text="Order UUID")
    status = serializers.ChoiceField(
        choices=[
            "pending_payment",
            "payment_confirmed",
            "awaiting_shipment",
            "shipped",
            "delivered",
            "cancelled",
            "refunded",
        ],
        help_text="Order status",
    )
    payment_status = serializers.ChoiceField(
        choices=["pending", "paid", "failed", "refunded"], help_text="Payment status"
    )
    buyer = serializers.DictField(help_text="Buyer information")
    items = serializers.ListField(child=OrderItemSerializer(), help_text="Order items")
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, help_text="Items subtotal")
    shipping_cost = serializers.DecimalField(max_digits=10, decimal_places=2, help_text="Shipping cost")
    tax_amount = serializers.DecimalField(max_digits=10, decimal_places=2, help_text="Tax amount")
    discount_amount = serializers.DecimalField(max_digits=10, decimal_places=2, help_text="Discount applied")
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2, help_text="Final total")
    shipping_address = ShippingAddressSerializer(help_text="Delivery address")
    buyer_notes = serializers.CharField(help_text="Buyer notes", required=False, allow_blank=True)
    tracking_number = serializers.CharField(help_text="Shipment tracking number", required=False, allow_null=True)
    shipping_carrier = serializers.CharField(help_text="Shipping carrier name", required=False, allow_null=True)
    shipped_at = serializers.DateTimeField(help_text="Shipment timestamp", required=False, allow_null=True)
    delivered_at = serializers.DateTimeField(help_text="Delivery timestamp", required=False, allow_null=True)
    created_at = serializers.DateTimeField(help_text="Order creation timestamp")


class OrderListResponseSerializer(serializers.Serializer):
    """Paginated order list response"""

    count = serializers.IntegerField(help_text="Total number of orders")
    page = serializers.IntegerField(help_text="Current page")
    page_size = serializers.IntegerField(help_text="Items per page")
    num_pages = serializers.IntegerField(help_text="Total pages")
    results = serializers.ListField(child=OrderListItemSerializer(), help_text="Order list")


class CancelOrderRequestSerializer(serializers.Serializer):
    """Request body for canceling an order"""

    reason = serializers.CharField(help_text="Reason for cancellation", required=False)


# ===== Review Response Serializers =====


class CreateReviewRequestSerializer(serializers.Serializer):
    """Request body for creating a review"""

    product_id = serializers.UUIDField(help_text="Product UUID to review")
    rating = serializers.IntegerField(min_value=1, max_value=5, help_text="Rating from 1 to 5 stars")
    title = serializers.CharField(max_length=200, help_text="Review title", required=False)
    comment = serializers.CharField(help_text="Review text", required=False)


class ReviewResponseSerializer(serializers.Serializer):
    """Review response"""

    id = serializers.IntegerField(help_text="Review ID")
    product = serializers.DictField(help_text="Product summary (id, name)")
    reviewer = serializers.DictField(help_text="Reviewer info (id, username)")
    rating = serializers.IntegerField(help_text="Rating (1-5 stars)")
    title = serializers.CharField(help_text="Review title")
    comment = serializers.CharField(help_text="Review text")
    verified_purchase = serializers.BooleanField(help_text="Whether reviewer purchased the product")
    created_at = serializers.DateTimeField(help_text="Review creation timestamp")
    updated_at = serializers.DateTimeField(help_text="Last update timestamp")


# ===== Search Response Serializers =====


class AutocompleteResponseSerializer(serializers.Serializer):
    """Autocomplete suggestions response"""

    suggestions = serializers.ListField(child=serializers.CharField(), help_text="List of product name suggestions")


class FilterOptionSerializer(serializers.Serializer):
    """Filter option (e.g., category, brand)"""

    id = serializers.IntegerField(help_text="Option ID", required=False)
    name = serializers.CharField(help_text="Option name")
    slug = serializers.CharField(help_text="URL slug", required=False)


class PriceRangeSerializer(serializers.Serializer):
    """Price range for filtering"""

    min = serializers.DecimalField(max_digits=10, decimal_places=2, help_text="Minimum price")
    max = serializers.DecimalField(max_digits=10, decimal_places=2, help_text="Maximum price")


class FiltersResponseSerializer(serializers.Serializer):
    """Available filter options response"""

    brands = serializers.ListField(child=serializers.CharField(), help_text="Available brands")
    categories = serializers.ListField(child=FilterOptionSerializer(), help_text="Available categories")
    price_range = PriceRangeSerializer(help_text="Price range in catalog")


# ===== Seller Response Serializers =====


class SellerProfileResponseSerializer(serializers.Serializer):
    """Seller profile response"""

    id = serializers.IntegerField(help_text="Seller user ID")
    username = serializers.CharField(help_text="Seller username")
    seller_rating = serializers.FloatField(help_text="Average seller rating (0-5)")
    total_sales = serializers.IntegerField(help_text="Total number of sales")
    products_count = serializers.IntegerField(help_text="Number of active products")
    joined_date = serializers.DateField(help_text="Date seller joined")
    bio = serializers.CharField(help_text="Seller bio/description", required=False)


# ===== Internal API Response Serializers =====


class InternalProductInfoSerializer(serializers.Serializer):
    """Internal API response for product info"""

    id = serializers.UUIDField(help_text="Product UUID")
    name = serializers.CharField(help_text="Product name")
    price = serializers.DecimalField(max_digits=10, decimal_places=2, help_text="Current price")
    stock_quantity = serializers.IntegerField(help_text="Available stock")
    is_active = serializers.BooleanField(help_text="Whether product is active")
    seller_id = serializers.IntegerField(help_text="Seller user ID")


class InternalOrderInfoSerializer(serializers.Serializer):
    """Internal API response for order info"""

    id = serializers.UUIDField(help_text="Order UUID")
    status = serializers.CharField(help_text="Order status")
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2, help_text="Order total")
    buyer_id = serializers.IntegerField(help_text="Buyer user ID")
    payment_status = serializers.CharField(help_text="Payment status")
    created_at = serializers.DateTimeField(help_text="Order creation timestamp")
