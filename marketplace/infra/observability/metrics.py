from prometheus_client import Counter, Gauge, Histogram


# Order Metrics
orders_placed_total = Counter("marketplace_orders_placed_total", "Total orders placed", ["status"])
order_value = Histogram(
    "marketplace_order_value",
    "Order value distribution",
    buckets=[10, 50, 100, 200, 500, 1000, 2000, 5000, float("inf")],
)

# Stock Metrics
stock_reservation_failures = Counter("marketplace_stock_reservation_failure", "Stock reservation failures")
stock_low_alert = Gauge("marketplace_stock_low_alert", "Products with low stock")

# Performance Metrics
cart_validation_duration = Histogram("marketplace_cart_validation_seconds", "Cart validation time")

# Add a counter for internal API calls
internal_api_calls_total = Counter(
    "marketplace_internal_api_calls_total", "Total internal API calls", ["endpoint", "status"]
)
