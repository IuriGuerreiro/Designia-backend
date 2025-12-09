"""
Prometheus Metrics Endpoint

Exposes Prometheus metrics for scraping.
This endpoint should be accessible to Prometheus but NOT exposed through Kong Gateway.
"""

from django.http import HttpResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest


def metrics(request):
    """
    Prometheus metrics endpoint.

    Returns metrics in Prometheus exposition format.
    Accessed by Prometheus at /api/auth/metrics

    **Security:** This endpoint has no authentication.
    In production, restrict access via firewall or network policy.

    Returns:
        HttpResponse: Prometheus metrics in text format
    """
    return HttpResponse(generate_latest(), content_type=CONTENT_TYPE_LATEST)
