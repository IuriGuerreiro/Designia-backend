"""
OpenTelemetry Distributed Tracing

Configures OpenTelemetry for distributed tracing across services.
Traces are exported to Jaeger for visualization and debugging.
"""

import logging
from typing import Optional

from opentelemetry import trace
from opentelemetry.instrumentation.django import DjangoInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)

_tracer: Optional[trace.Tracer] = None
_initialized = False


def setup_tracing(
    service_name: str = "authentication-service",
    jaeger_host: str = "localhost",
    jaeger_port: int = 6831,
    enable: bool = True,
) -> None:
    """
    Initialize OpenTelemetry tracing with Jaeger exporter.

    Args:
        service_name: Name of the service for tracing
        jaeger_host: Jaeger agent hostname
        jaeger_port: Jaeger agent port (default: 6831 for UDP)
        enable: Enable/disable tracing

    Example:
        setup_tracing(
            service_name="authentication-service",
            jaeger_host="jaeger",
            jaeger_port=6831
        )
    """
    global _initialized

    if _initialized:
        logger.warning("Tracing already initialized. Skipping.")
        return

    if not enable:
        logger.info("Tracing disabled via configuration")
        return

    try:
        # Create resource with service name
        resource = Resource(attributes={SERVICE_NAME: service_name})

        # Create tracer provider
        tracer_provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(tracer_provider)

        # Configure Jaeger exporter
        try:
            from opentelemetry.exporter.jaeger.thrift import JaegerExporter

            jaeger_exporter = JaegerExporter(
                agent_host_name=jaeger_host,
                agent_port=jaeger_port,
            )

            # Add span processor (batches spans for efficiency)
            tracer_provider.add_span_processor(BatchSpanProcessor(jaeger_exporter))

            logger.info(f"Jaeger tracing configured: {jaeger_host}:{jaeger_port}")
        except ImportError:
            logger.warning("Jaeger exporter not available. Traces will not be exported.")
        except Exception as e:
            logger.error(f"Failed to configure Jaeger exporter: {e}")

        # Auto-instrument Django (traces all HTTP requests)
        DjangoInstrumentor().instrument()
        logger.info("Django auto-instrumentation enabled")

        # Auto-instrument requests library (traces outgoing HTTP calls)
        RequestsInstrumentor().instrument()
        logger.info("Requests auto-instrumentation enabled")

        _initialized = True
        logger.info(f"OpenTelemetry tracing initialized for service: {service_name}")

    except Exception as e:
        logger.error(f"Failed to initialize tracing: {e}")


def get_tracer(name: str = __name__) -> trace.Tracer:
    """
    Get tracer instance for creating custom spans.

    Args:
        name: Tracer name (usually __name__ of module)

    Returns:
        Tracer instance

    Example:
        tracer = get_tracer(__name__)

        with tracer.start_as_current_span("my_operation"):
            # Your code here
            pass
    """
    global _tracer

    if _tracer is None:
        _tracer = trace.get_tracer(name)

    return _tracer


def add_span_attributes(span: trace.Span, **attributes) -> None:
    """
    Add custom attributes to current span.

    Args:
        span: Span to add attributes to
        **attributes: Key-value pairs to add

    Example:
        with tracer.start_as_current_span("login") as span:
            add_span_attributes(
                span,
                user_id="123",
                email="user@example.com",
                requires_2fa=True
            )
    """
    for key, value in attributes.items():
        span.set_attribute(key, str(value))


def trace_function(operation_name: Optional[str] = None):
    """
    Decorator to trace a function execution.

    Args:
        operation_name: Name for the span (defaults to function name)

    Example:
        @trace_function("authenticate_user")
        def login(email, password):
            # Your code here
            pass
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            tracer = get_tracer()
            span_name = operation_name or f"{func.__module__}.{func.__name__}"

            with tracer.start_as_current_span(span_name):
                return func(*args, **kwargs)

        return wrapper

    return decorator
