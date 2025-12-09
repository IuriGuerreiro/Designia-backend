"""
Health Check Endpoints

Kubernetes-compatible health probes for liveness and readiness checks.
"""

import logging

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse

logger = logging.getLogger(__name__)


def health_live(request):
    """
    Liveness probe: Is the process alive?

    Returns 200 if the Django process is running.
    Kubernetes uses this to restart crashed pods.

    **Always returns 200** unless the process is completely dead.

    Returns:
        JsonResponse: {'status': 'ok'}
    """
    return JsonResponse({"status": "ok"}, status=200)


def health_ready(request):
    """
    Readiness probe: Can the service handle requests?

    Checks critical dependencies:
    - Database connection
    - Redis connection (cache + event bus)

    Returns:
        JsonResponse: Status and check details
        Status Code: 200 (ready) or 503 (not ready)

    Kubernetes uses this to route traffic only to ready pods.
    """
    checks = {"database": check_database(), "redis": check_redis(), "event_bus": check_event_bus()}

    all_ok = all(checks.values())
    status_code = 200 if all_ok else 503

    return JsonResponse({"status": "ready" if all_ok else "not_ready", "checks": checks}, status=status_code)


def check_database():
    """
    Check database connection.

    Returns:
        bool: True if database is accessible
    """
    try:
        connection.ensure_connection()
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False


def check_redis():
    """
    Check Redis connection (Django cache).

    Returns:
        bool: True if Redis is accessible
    """
    try:
        cache.set("health_check", "ok", timeout=1)
        result = cache.get("health_check")
        return result == "ok"
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return False


def check_event_bus():
    """
    Check event bus connection (Redis).

    Returns:
        bool: True if event bus is accessible
    """
    try:
        from authentication.infra.events.redis_event_bus import get_event_bus

        event_bus = get_event_bus()
        # Ping Redis to check connection
        event_bus.redis_client.ping()
        return True
    except Exception as e:
        logger.error(f"Event bus health check failed: {e}")
        return False
