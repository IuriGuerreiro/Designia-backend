"""
Domain Events for Authentication.

Domain events represent important business occurrences that other parts of the system
might want to react to. This enables loose coupling and extensibility.

Events are dispatched using Django signals for now. In the future, these can be
published to an event bus (Redis pub/sub, RabbitMQ, etc.) for microservices.
"""

from dataclasses import dataclass
from typing import Any, Optional

from django.dispatch import Signal

# ===== Event Signals =====

# Authentication Events
user_registered = Signal()  # sender=user, email_sent=bool
user_email_verified = Signal()  # sender=user
user_login_successful = Signal()  # sender=user, ip_address=str
user_login_failed = Signal()  # email=str, reason=str, ip_address=str
user_2fa_enabled = Signal()  # sender=user
user_2fa_disabled = Signal()  # sender=user

# Seller Application Events
seller_application_submitted = Signal()  # sender=application, is_resubmission=bool
seller_application_approved = Signal()  # sender=application, admin_user=user
seller_application_rejected = Signal()  # sender=application, admin_user=user, reason=str

# Profile Events
profile_updated = Signal()  # sender=user, updated_fields=list
profile_picture_uploaded = Signal()  # sender=user, file_key=str
profile_picture_deleted = Signal()  # sender=user


# ===== Event Data Classes =====


@dataclass
class UserRegisteredEvent:
    """Event data for user registration."""

    user: Any  # CustomUser instance
    email_sent: bool
    registration_ip: Optional[str] = None


@dataclass
class UserEmailVerifiedEvent:
    """Event data for email verification."""

    user: Any  # CustomUser instance
    verification_ip: Optional[str] = None


@dataclass
class UserLoginEvent:
    """Event data for successful login."""

    user: Any  # CustomUser instance
    ip_address: Optional[str] = None
    required_2fa: bool = False


@dataclass
class UserLoginFailedEvent:
    """Event data for failed login attempt."""

    email: str
    reason: str  # wrong_password, user_not_found, email_not_verified, etc.
    ip_address: Optional[str] = None


@dataclass
class SellerApplicationSubmittedEvent:
    """Event data for seller application submission."""

    application: Any  # SellerApplication instance
    is_resubmission: bool


@dataclass
class SellerApplicationApprovedEvent:
    """Event data for seller application approval."""

    application: Any  # SellerApplication instance
    admin_user: Any  # CustomUser instance (admin)
    new_seller: Any  # CustomUser instance (newly approved seller)


@dataclass
class SellerApplicationRejectedEvent:
    """Event data for seller application rejection."""

    application: Any  # SellerApplication instance
    admin_user: Any  # CustomUser instance (admin)
    reason: str


@dataclass
class ProfileUpdatedEvent:
    """Event data for profile update."""

    user: Any  # CustomUser instance
    updated_fields: list
    profile_completion: int  # Percentage


# ===== Event Dispatcher Helper =====


class EventDispatcher:
    """
    Helper class for dispatching domain events.

    Centralizes event dispatching logic and provides logging.
    """

    @staticmethod
    def dispatch_user_registered(user, email_sent: bool, ip_address: Optional[str] = None):
        """Dispatch user registered event."""
        import logging

        from infrastructure.events.redis_event_bus import get_event_bus

        logger = logging.getLogger(__name__)

        logger.info(f"[EVENT] User registered: {user.email} (email_sent={email_sent})")

        # Legacy Signal
        user_registered.send(sender=user.__class__, user=user, email_sent=email_sent, ip_address=ip_address)

        # Redis Event Bus
        try:
            get_event_bus().publish(
                "user.registered",
                {"user_id": str(user.id), "email": user.email, "email_sent": email_sent, "ip_address": ip_address},
            )
        except Exception as e:
            logger.error(f"Failed to publish user.registered event: {e}")

    @staticmethod
    def dispatch_user_email_verified(user, ip_address: Optional[str] = None):
        """Dispatch email verified event."""
        import logging

        from infrastructure.events.redis_event_bus import get_event_bus

        logger = logging.getLogger(__name__)

        logger.info(f"[EVENT] Email verified: {user.email}")

        # Legacy Signal
        user_email_verified.send(sender=user.__class__, user=user, ip_address=ip_address)

        # Redis Event Bus
        try:
            get_event_bus().publish(
                "user.verified", {"user_id": str(user.id), "email": user.email, "ip_address": ip_address}
            )
        except Exception as e:
            logger.error(f"Failed to publish user.verified event: {e}")

    @staticmethod
    def dispatch_user_login_successful(user, ip_address: Optional[str] = None, required_2fa: bool = False):
        """Dispatch successful login event."""
        import logging

        from infrastructure.events.redis_event_bus import get_event_bus

        logger = logging.getLogger(__name__)

        logger.info(f"[EVENT] User login successful: {user.email} (2FA={required_2fa})")

        # Legacy Signal
        user_login_successful.send(sender=user.__class__, user=user, ip_address=ip_address, required_2fa=required_2fa)

        # Redis Event Bus
        try:
            get_event_bus().publish(
                "user.login_successful",
                {"user_id": str(user.id), "email": user.email, "ip_address": ip_address, "required_2fa": required_2fa},
            )
        except Exception as e:
            logger.error(f"Failed to publish user.login_successful event: {e}")

    @staticmethod
    def dispatch_user_login_failed(email: str, reason: str, ip_address: Optional[str] = None):
        """Dispatch failed login event."""
        import logging

        from infrastructure.events.redis_event_bus import get_event_bus

        logger = logging.getLogger(__name__)

        logger.warning(f"[EVENT] Login failed: {email} - {reason}")

        # Legacy Signal
        user_login_failed.send(sender=None, email=email, reason=reason, ip_address=ip_address)

        # Redis Event Bus
        try:
            get_event_bus().publish("user.login_failed", {"email": email, "reason": reason, "ip_address": ip_address})
        except Exception as e:
            logger.error(f"Failed to publish user.login_failed event: {e}")

    @staticmethod
    def dispatch_user_2fa_enabled(user):
        """Dispatch 2FA enabled event."""
        import logging

        from infrastructure.events.redis_event_bus import get_event_bus

        logger = logging.getLogger(__name__)

        logger.info(f"[EVENT] 2FA enabled: {user.email}")

        # Legacy Signal
        user_2fa_enabled.send(sender=user.__class__, user=user)

        # Redis Event Bus
        try:
            get_event_bus().publish("user.2fa_enabled", {"user_id": str(user.id), "email": user.email})
        except Exception as e:
            logger.error(f"Failed to publish user.2fa_enabled event: {e}")

    @staticmethod
    def dispatch_user_2fa_disabled(user):
        """Dispatch 2FA disabled event."""
        import logging

        from infrastructure.events.redis_event_bus import get_event_bus

        logger = logging.getLogger(__name__)

        logger.info(f"[EVENT] 2FA disabled: {user.email}")

        # Legacy Signal
        user_2fa_disabled.send(sender=user.__class__, user=user)

        # Redis Event Bus
        try:
            get_event_bus().publish("user.2fa_disabled", {"user_id": str(user.id), "email": user.email})
        except Exception as e:
            logger.error(f"Failed to publish user.2fa_disabled event: {e}")

    @staticmethod
    def dispatch_seller_application_submitted(application, is_resubmission: bool):
        """Dispatch seller application submitted event."""
        import logging

        from infrastructure.events.redis_event_bus import get_event_bus

        logger = logging.getLogger(__name__)

        logger.info(
            f"[EVENT] Seller application {'resubmitted' if is_resubmission else 'submitted'}: "
            f"{application.user.email} (app_id={application.id})"
        )

        # Legacy Signal
        seller_application_submitted.send(
            sender=application.__class__, application=application, is_resubmission=is_resubmission
        )

        # Redis Event Bus
        try:
            get_event_bus().publish(
                "seller.application_submitted",
                {
                    "application_id": application.id,
                    "user_id": str(application.user.id),
                    "seller_type": application.seller_type,
                    "is_resubmission": is_resubmission,
                },
            )
        except Exception as e:
            logger.error(f"Failed to publish seller.application_submitted event: {e}")

    @staticmethod
    def dispatch_seller_application_approved(application, admin_user):
        """Dispatch seller application approved event."""
        import logging

        from infrastructure.events.redis_event_bus import get_event_bus

        logger = logging.getLogger(__name__)

        logger.info(
            f"[EVENT] Seller application approved: {application.user.email} "
            f"by admin {admin_user.email} (app_id={application.id})"
        )

        # Legacy Signal
        seller_application_approved.send(
            sender=application.__class__, application=application, admin_user=admin_user, new_seller=application.user
        )

        # Redis Event Bus
        try:
            get_event_bus().publish(
                "seller.approved",
                {
                    "application_id": application.id,
                    "user_id": str(application.user.id),
                    "seller_type": application.seller_type,
                    "approved_by": str(admin_user.id),
                },
            )
        except Exception as e:
            logger.error(f"Failed to publish seller.approved event: {e}")

    @staticmethod
    def dispatch_seller_application_rejected(application, admin_user, reason: str):
        """Dispatch seller application rejected event."""
        import logging

        from infrastructure.events.redis_event_bus import get_event_bus

        logger = logging.getLogger(__name__)

        logger.info(
            f"[EVENT] Seller application rejected: {application.user.email} "
            f"by admin {admin_user.email} (app_id={application.id})"
        )

        # Legacy Signal
        seller_application_rejected.send(
            sender=application.__class__, application=application, admin_user=admin_user, reason=reason
        )

        # Redis Event Bus
        try:
            get_event_bus().publish(
                "seller.rejected",
                {
                    "application_id": application.id,
                    "user_id": str(application.user.id),
                    "reason": reason,
                    "rejected_by": str(admin_user.id),
                },
            )
        except Exception as e:
            logger.error(f"Failed to publish seller.rejected event: {e}")

    @staticmethod
    def dispatch_profile_updated(user, updated_fields: list, profile_completion: int):
        """Dispatch profile updated event."""
        import logging

        from infrastructure.events.redis_event_bus import get_event_bus

        logger = logging.getLogger(__name__)

        logger.info(
            f"[EVENT] Profile updated: {user.email} "
            f"(fields={len(updated_fields)}, completion={profile_completion}%)"
        )

        # Legacy Signal
        profile_updated.send(
            sender=user.__class__, user=user, updated_fields=updated_fields, profile_completion=profile_completion
        )

        # Redis Event Bus
        try:
            get_event_bus().publish(
                "profile.updated",
                {"user_id": str(user.id), "updated_fields": updated_fields, "profile_completion": profile_completion},
            )
        except Exception as e:
            logger.error(f"Failed to publish profile.updated event: {e}")

    @staticmethod
    def dispatch_profile_picture_uploaded(user, file_key: str):
        """Dispatch profile picture uploaded event."""
        import logging

        from infrastructure.events.redis_event_bus import get_event_bus

        logger = logging.getLogger(__name__)

        logger.info(f"[EVENT] Profile picture uploaded: {user.email}")

        # Legacy Signal
        profile_picture_uploaded.send(sender=user.__class__, user=user, file_key=file_key)

        # Redis Event Bus
        try:
            get_event_bus().publish("profile.picture_uploaded", {"user_id": str(user.id), "file_key": file_key})
        except Exception as e:
            logger.error(f"Failed to publish profile.picture_uploaded event: {e}")

    @staticmethod
    def dispatch_profile_picture_deleted(user):
        """Dispatch profile picture deleted event."""
        import logging

        from infrastructure.events.redis_event_bus import get_event_bus

        logger = logging.getLogger(__name__)

        logger.info(f"[EVENT] Profile picture deleted: {user.email}")

        # Legacy Signal
        profile_picture_deleted.send(sender=user.__class__, user=user)

        # Redis Event Bus
        try:
            get_event_bus().publish("profile.picture_deleted", {"user_id": str(user.id)})
        except Exception as e:
            logger.error(f"Failed to publish profile.picture_deleted event: {e}")
