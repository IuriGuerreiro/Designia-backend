from django.conf import settings
from rest_framework import permissions


class IsStaffOrInternalService(permissions.BasePermission):
    """
    Custom permission to allow access only to staff users or internal services.
    Internal services are identified by whitelisted IP addresses.
    """

    def has_permission(self, request, view):
        # Allow if user is staff
        if request.user and request.user.is_staff:
            return True

        # Allow if request is from a whitelisted internal IP
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0]
        else:
            ip = request.META.get("REMOTE_ADDR")

        internal_ips = getattr(settings, "INTERNAL_SERVICE_IPS", [])

        return ip in internal_ips
