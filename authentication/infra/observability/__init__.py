"""
Observability Infrastructure

OpenTelemetry tracing and Prometheus metrics for authentication service.
Provides distributed tracing, metrics collection, and performance monitoring.
"""

from .metrics import (  # Login metrics; Seller metrics; JWT metrics
    jwt_validation_total,
    login_duration,
    login_failed,
    login_total,
    seller_applications_pending,
    seller_applications_total,
)
from .tracing import get_tracer, setup_tracing

__all__ = [
    "setup_tracing",
    "get_tracer",
    "login_total",
    "login_failed",
    "login_duration",
    "seller_applications_pending",
    "seller_applications_total",
    "jwt_validation_total",
]
