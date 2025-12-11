"""
Signal Handlers for Authentication Events.

This module contains signal handlers that respond to domain events.
Handlers can perform side effects like sending notifications, logging analytics,
updating related models, etc.

Register handlers by connecting them to signals in apps.py ready() method.
"""

import logging

from django.dispatch import receiver

from .domain.events import (
    profile_picture_deleted,
    profile_picture_uploaded,
    profile_updated,
    seller_application_approved,
    seller_application_rejected,
    seller_application_submitted,
    user_email_verified,
    user_login_failed,
    user_login_successful,
    user_registered,
)


logger = logging.getLogger(__name__)


# ===== Authentication Event Handlers =====


@receiver(user_registered)
def handle_user_registered(sender, user, email_sent, ip_address=None, **kwargs):
    """
    Handle user registration event.

    Example use cases:
    - Send welcome email (if not already sent)
    - Create analytics event
    - Initialize user preferences
    - Trigger onboarding workflow
    """
    logger.info(f"[SIGNAL] User registered: {user.email} from IP {ip_address or 'unknown'}")

    # Example: You could send a welcome email here
    # Example: Track analytics
    # from analytics import track_event
    # track_event('user_registered', user.id, {'email_sent': email_sent})

    # Example: Initialize user preferences
    # UserPreferences.objects.get_or_create(user=user, defaults={'theme': 'light'})


@receiver(user_email_verified)
def handle_user_email_verified(sender, user, ip_address=None, **kwargs):
    """
    Handle email verification event.

    Example use cases:
    - Send welcome email (now that email is verified)
    - Grant access to restricted features
    - Track conversion funnel
    """
    logger.info(f"[SIGNAL] Email verified: {user.email}")

    # Example: Send welcome email
    # send_welcome_email(user)

    # Example: Track analytics
    # track_event('email_verified', user.id)


@receiver(user_login_successful)
def handle_user_login_successful(sender, user, ip_address=None, required_2fa=False, **kwargs):
    """
    Handle successful login event.

    Example use cases:
    - Update last login timestamp (Django does this automatically)
    - Track login analytics
    - Check for suspicious login patterns
    - Send security alert for new device
    """
    logger.info(f"[SIGNAL] Login successful: {user.email} (2FA={required_2fa})")

    # Example: Track login analytics
    # track_event('user_login', user.id, {'ip': ip_address, '2fa': required_2fa})

    # Example: Check for suspicious activity
    # SecurityMonitor.check_login_pattern(user, ip_address)


@receiver(user_login_failed)
def handle_user_login_failed(sender, email, reason, ip_address=None, **kwargs):
    """
    Handle failed login event.

    Example use cases:
    - Track failed login attempts for rate limiting
    - Alert on brute force attempts
    - Track analytics for login issues
    """
    logger.warning(f"[SIGNAL] Login failed: {email} - {reason} from IP {ip_address or 'unknown'}")

    # Example: Track failed attempts for rate limiting
    # RateLimiter.record_failed_login(email, ip_address)

    # Example: Alert on suspicious activity
    # if RateLimiter.get_failed_count(email) > 5:
    #     SecurityMonitor.alert_brute_force(email, ip_address)


# ===== Seller Application Event Handlers =====


@receiver(seller_application_submitted)
def handle_seller_application_submitted(sender, application, is_resubmission, **kwargs):
    """
    Handle seller application submission event.

    Example use cases:
    - Send confirmation email to applicant
    - Notify admins of new application
    - Track analytics
    - Trigger review workflow
    """
    logger.info(
        f"[SIGNAL] Seller application {'resubmitted' if is_resubmission else 'submitted'}: {application.user.email}"
    )

    # Example: Send confirmation email to applicant
    # send_application_confirmation_email(application.user)

    # Example: Notify admins
    # notify_admins_new_application(application)

    # Example: Track analytics
    # track_event('seller_application_submitted', application.user.id, {
    #     'is_resubmission': is_resubmission,
    #     'seller_type': application.seller_type
    # })


@receiver(seller_application_approved)
def handle_seller_application_approved(sender, application, admin_user, new_seller, **kwargs):
    """
    Handle seller application approval event.

    Example use cases:
    - Send approval email to new seller
    - Grant seller permissions
    - Send welcome guide for sellers
    - Notify other admins
    - Track conversion analytics
    """
    logger.info(f"[SIGNAL] Seller application approved: {new_seller.email} by {admin_user.email}")

    # Example: Send approval email with seller onboarding guide
    # send_seller_approval_email(new_seller, application)

    # Example: Grant additional permissions
    # SellerPermissions.initialize_for_user(new_seller)

    # Example: Track analytics
    # track_event('seller_approved', new_seller.id, {
    #     'seller_type': application.seller_type,
    #     'approved_by': admin_user.id
    # })


@receiver(seller_application_rejected)
def handle_seller_application_rejected(sender, application, admin_user, reason, **kwargs):
    """
    Handle seller application rejection event.

    Example use cases:
    - Send rejection email with reason
    - Track rejection analytics
    - Schedule follow-up communication
    """
    logger.info(f"[SIGNAL] Seller application rejected: {application.user.email} by {admin_user.email}")

    # Example: Send rejection email
    # send_seller_rejection_email(application.user, reason)

    # Example: Track analytics
    # track_event('seller_rejected', application.user.id, {
    #     'reason': reason,
    #     'rejected_by': admin_user.id
    # })


# ===== Profile Event Handlers =====


@receiver(profile_updated)
def handle_profile_updated(sender, user, updated_fields, profile_completion, **kwargs):
    """
    Handle profile update event.

    Example use cases:
    - Track which fields are most commonly updated
    - Send profile completion milestone emails
    - Update search index for user profiles
    - Trigger recommendations based on profile data
    """
    logger.info(
        f"[SIGNAL] Profile updated: {user.email} - {len(updated_fields)} fields (completion={profile_completion}%)"
    )

    # Example: Send milestone email for profile completion
    # if profile_completion == 100 and 'bio' in updated_fields:
    #     send_profile_complete_email(user)

    # Example: Update search index
    # ProfileSearchIndex.update(user)

    # Example: Track analytics
    # track_event('profile_updated', user.id, {
    #     'fields': updated_fields,
    #     'completion': profile_completion
    # })


@receiver(profile_picture_uploaded)
def handle_profile_picture_uploaded(sender, user, file_key, **kwargs):
    """
    Handle profile picture upload event.

    Example use cases:
    - Generate thumbnails
    - Update CDN cache
    - Notify connections of profile update
    - Track analytics
    """
    logger.info(f"[SIGNAL] Profile picture uploaded: {user.email}")

    # Example: Generate thumbnails (if needed)
    # ThumbnailGenerator.generate_for_profile(user, file_key)

    # Example: Track analytics
    # track_event('profile_picture_uploaded', user.id)


@receiver(profile_picture_deleted)
def handle_profile_picture_deleted(sender, user, **kwargs):
    """
    Handle profile picture deletion event.

    Example use cases:
    - Clean up CDN cache
    - Delete related thumbnails
    - Track analytics
    """
    logger.info(f"[SIGNAL] Profile picture deleted: {user.email}")

    # Example: Clean up thumbnails
    # ThumbnailGenerator.delete_for_profile(user)

    # Example: Track analytics
    # track_event('profile_picture_deleted', user.id)


# ===== Example: Custom Business Logic Handlers =====

# You can add more handlers here for custom business logic
# Example: Send email when seller gets their first order
# Example: Award badges for profile completion milestones
# Example: Trigger marketing automation workflows
# Example: Update external CRM systems
