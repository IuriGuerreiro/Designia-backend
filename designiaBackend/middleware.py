"""Custom middleware helpers for the Designia backend."""

from __future__ import annotations

from typing import Callable


class JWTCSRFBypassMiddleware:
    """Skip CSRF enforcement for stateless JWT authenticated requests.

    Django's ``CsrfViewMiddleware`` enforces CSRF validation for every mutating
    request, regardless of whether the client relies on cookies. For our API we
    exclusively rely on Authorization headers (JWT Bearer tokens). Enforcing the
    CSRF check for these requests breaks legitimate clients even though the
    attack surface is already mitigated by the absence of cookies. This
    middleware marks those requests as safe so that CSRF protection continues to
    guard any session-based endpoints that might exist in the project without
    blocking our stateless APIs.
    """

    def __init__(self, get_response: Callable):
        self.get_response = get_response

    def __call__(self, request):
        authorization = request.META.get("HTTP_AUTHORIZATION", "")
        if authorization.lower().startswith("bearer "):
            # Tell CsrfViewMiddleware to skip enforcement for this request so that
            # stateless clients do not need to fetch CSRF tokens. We also attach
            # a diagnostic reason to help with debugging in logs.
            request._dont_enforce_csrf_checks = True  # type: ignore[attr-defined]
            request.META.setdefault("CSRF_SKIP_REASON", "jwt-bearer")
        return self.get_response(request)

