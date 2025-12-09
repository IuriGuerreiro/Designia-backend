"""
Prometheus Metrics

Defines all Prometheus metrics for authentication service monitoring.
Metrics are exposed at /api/auth/metrics for Prometheus scraping.
"""

from prometheus_client import Counter, Gauge, Histogram

# ===== Login Metrics =====

login_total = Counter("auth_login_total", "Total login attempts", ["status", "requires_2fa"])
"""
Total login attempts counter.
Labels: status (success/failed), requires_2fa (true/false)

Example:
    login_total.labels(status='success', requires_2fa='false').inc()
"""

login_failed = Counter("auth_login_failed", "Failed login attempts", ["reason"])
"""
Failed login attempts counter.
Labels: reason (invalid_credentials, email_not_verified, account_disabled, etc.)

Example:
    login_failed.labels(reason='invalid_credentials').inc()
"""

login_duration = Histogram(
    "auth_login_duration_seconds", "Login request duration in seconds", buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)
"""
Login duration histogram.
Tracks time taken for login operations.

Example:
    with login_duration.time():
        # Login logic here
        pass
"""


# ===== Registration Metrics =====

registration_total = Counter("auth_registration_total", "Total registration attempts", ["status"])
"""
Total registration attempts.
Labels: status (success/failed)
"""

registration_failed = Counter("auth_registration_failed", "Failed registration attempts", ["reason"])
"""
Failed registrations counter.
Labels: reason (email_exists, validation_error, etc.)
"""


# ===== Email Verification Metrics =====

email_verification_sent = Counter("auth_email_verification_sent", "Total verification emails sent", ["type"])
"""
Email verification counter.
Labels: type (registration, resend)
"""

email_verification_completed = Counter("auth_email_verification_completed", "Total successful email verifications")
"""
Successful email verifications counter.
"""


# ===== 2FA Metrics =====

two_fa_codes_sent = Counter("auth_2fa_codes_sent", "Total 2FA codes sent", ["purpose"])
"""
2FA codes sent counter.
Labels: purpose (login, settings_change, etc.)
"""

two_fa_validation_total = Counter("auth_2fa_validation_total", "Total 2FA validations", ["status"])
"""
2FA validation attempts.
Labels: status (success/failed)
"""


# ===== Seller Application Metrics =====

seller_applications_total = Counter("auth_seller_applications_total", "Total seller applications", ["status"])
"""
Seller applications counter.
Labels: status (submitted, approved, rejected)
"""

seller_applications_pending = Gauge("auth_seller_applications_pending", "Number of pending seller applications")
"""
Current number of pending seller applications.
This is a gauge that should be updated periodically.
"""


# ===== JWT Metrics =====

jwt_validation_total = Counter("auth_jwt_validation_total", "Total JWT validations", ["status"])
"""
JWT validation attempts.
Labels: status (valid/invalid/expired)
"""

jwt_generation_total = Counter("auth_jwt_generation_total", "Total JWT tokens generated", ["token_type"])
"""
JWT token generation counter.
Labels: token_type (access/refresh)
"""


# ===== Profile Metrics =====

profile_updates_total = Counter("auth_profile_updates_total", "Total profile updates")
"""
Profile update counter.
"""

profile_picture_uploads = Counter("auth_profile_picture_uploads", "Total profile picture uploads", ["status"])
"""
Profile picture uploads.
Labels: status (success/failed)
"""


# ===== Google OAuth Metrics =====

google_oauth_total = Counter("auth_google_oauth_total", "Total Google OAuth attempts", ["status"])
"""
Google OAuth counter.
Labels: status (success/failed)
"""


# ===== General Authentication Metrics =====

active_sessions = Gauge("auth_active_sessions", "Number of active user sessions")
"""
Current number of active user sessions.
Should be updated periodically from session store.
"""

password_reset_requests = Counter("auth_password_reset_requests", "Total password reset requests")
"""
Password reset requests counter.
"""


# ===== Helper Functions =====


def record_login_attempt(success: bool, requires_2fa: bool, reason: str = None):
    """
    Record login attempt metrics.

    Args:
        success: Whether login was successful
        requires_2fa: Whether 2FA is required
        reason: Failure reason (if failed)
    """
    status = "success" if success else "failed"
    login_total.labels(status=status, requires_2fa=str(requires_2fa).lower()).inc()

    if not success and reason:
        login_failed.labels(reason=reason).inc()


def record_registration_attempt(success: bool, reason: str = None):
    """
    Record registration attempt metrics.

    Args:
        success: Whether registration was successful
        reason: Failure reason (if failed)
    """
    status = "success" if success else "failed"
    registration_total.labels(status=status).inc()

    if not success and reason:
        registration_failed.labels(reason=reason).inc()


def record_seller_application(status: str):
    """
    Record seller application metrics.

    Args:
        status: Application status (submitted/approved/rejected)
    """
    seller_applications_total.labels(status=status).inc()


def record_jwt_validation(valid: bool, expired: bool = False):
    """
    Record JWT validation metrics.

    Args:
        valid: Whether token is valid
        expired: Whether token is expired
    """
    if expired:
        status = "expired"
    elif valid:
        status = "valid"
    else:
        status = "invalid"

    jwt_validation_total.labels(status=status).inc()
