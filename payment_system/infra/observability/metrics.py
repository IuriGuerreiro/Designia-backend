from prometheus_client import Counter, Gauge


# Define Prometheus metrics
payment_volume_total = Counter("payment_volume_total", "Total payment volume processed", ["currency", "status"])

payout_volume_total = Counter("payout_volume_total", "Total payout volume processed", ["currency", "status"])

active_holds_value = Gauge("active_holds_value", "Current value of active payment holds", ["currency"])

# You can add more metrics as needed
# e.g., payment_latency_seconds = Histogram(...)
# e.g., webhook_processing_time = Histogram(...)
# e.g., failed_refund_total = Counter(...)
