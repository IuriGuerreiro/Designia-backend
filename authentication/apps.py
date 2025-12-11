import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class AuthenticationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "authentication"

    def ready(self):
        """
        Initialize authentication context.
        """
        # Import legacy signal handlers
        try:
            import authentication.signals  # noqa: F401
        except ImportError:
            pass

        # Register Event Bus Listeners
        try:
            from authentication.infra.events.listeners import register_authentication_listeners
            from infrastructure.events.redis_event_bus import get_event_bus

            # Register listeners
            register_authentication_listeners()

            # Start listening thread (if using Redis)
            # In production/uWSGI, this might need care to not spawn too many threads,
            # or rely on a separate worker process. For now, following spec.
            event_bus = get_event_bus()
            event_bus.start_listening()

        except Exception as e:
            logger.warning(f"Failed to initialize Event Bus listeners: {e}")

        # Initialize OpenTelemetry Tracing (Phase 3)
        try:
            from django.conf import settings

            from authentication.infra.observability.tracing import setup_tracing

            # Get config from Django settings
            jaeger_host = getattr(settings, "JAEGER_AGENT_HOST", "localhost")
            jaeger_port = getattr(settings, "JAEGER_AGENT_PORT", 6831)
            tracing_enabled = getattr(settings, "OTEL_TRACING_ENABLED", True)

            setup_tracing(
                service_name="authentication-service",
                jaeger_host=jaeger_host,
                jaeger_port=jaeger_port,
                enable=tracing_enabled,
            )

            logger.info("OpenTelemetry tracing initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize OpenTelemetry tracing: {e}")
