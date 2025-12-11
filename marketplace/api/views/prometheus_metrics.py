from django.http import HttpResponse
from prometheus_client import generate_latest
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny


@api_view(["GET"])
@permission_classes([AllowAny])
def marketplace_prometheus_metrics(request):
    """
    Exposes Prometheus metrics for the marketplace app.
    """
    metrics_content = generate_latest()
    return HttpResponse(metrics_content, content_type="text/plain; version=0.0.4; charset=utf-8")
