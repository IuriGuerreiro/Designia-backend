"""
Celery Tasks for GDPR Compliance

Story 6.1 - Data Export and Account Deletion
"""

import json
import logging
from io import BytesIO

from celery import shared_task
from django.template.loader import render_to_string
from django.utils import timezone

from utils.email_utils import send_email


logger = logging.getLogger(__name__)


@shared_task(name="export_user_data")
def export_user_data_task(user_id: str):
    """
    Celery task to export all user data for GDPR compliance.

    Process:
    1. Collect all user-related data
    2. Generate JSON file
    3. Upload to S3 with time-limited access
    4. Send email with download link

    Args:
        user_id: UUID of the user requesting export
    """
    from authentication.domain.events import EventDispatcher
    from authentication.domain.models import CustomUser
    from authentication.domain.services.profile_service import ProfileService
    from authentication.infra.storage.s3_storage_provider import S3StorageProvider

    logger.info(f"Starting data export for user {user_id}")

    try:
        # Get user
        user = CustomUser.objects.get(id=user_id)
        user_email = user.email

        # Dispatch event
        EventDispatcher.dispatch_data_export_requested(user_id=user_id, email=user_email)

        # Collect user data via service
        service = ProfileService(storage_provider=S3StorageProvider())
        user_data = service.collect_user_data(user)

        # Generate JSON content
        json_content = json.dumps(user_data, indent=2, ensure_ascii=False)
        json_bytes = json_content.encode("utf-8")

        # Upload to S3 (wrap bytes in BytesIO for file-like interface)
        storage = S3StorageProvider()
        export_filename = f"gdpr-exports/{user_id}/data_export_{timezone.now().strftime('%Y%m%d_%H%M%S')}.json"

        file_obj = BytesIO(json_bytes)
        file_obj.name = "data_export.json"  # S3 provider may need a name attribute

        success, file_key_or_error, _ = storage.upload_file(
            file=file_obj,
            path=export_filename,
            public=False,
            validate_image=False,  # Allow JSON files
        )

        if not success:
            logger.error(f"Failed to upload export file for user {user_id}: {file_key_or_error}")
            _send_export_failure_email(user)
            return f"Failed: {file_key_or_error}"

        # Generate time-limited download URL (valid for 24 hours)
        download_url = storage.get_file_url(export_filename, expires_in=86400)

        # Send email with download link
        _send_export_success_email(user, download_url)

        logger.info(f"Data export completed for user {user_id}")
        return f"Export completed for user {user_id}"

    except CustomUser.DoesNotExist:
        logger.error(f"User not found for export: {user_id}")
        return f"Failed: User {user_id} not found"

    except Exception as e:
        logger.exception(f"Error in export_user_data_task for user {user_id}: {e}")
        try:
            user = CustomUser.objects.get(id=user_id)
            _send_export_failure_email(user)
        except Exception:
            pass
        raise


def _send_export_success_email(user, download_url: str):
    """Send email with data export download link."""
    context = {
        "user": user,
        "download_url": download_url,
        "expiry_hours": 24,
        "current_year": timezone.now().year,
    }

    subject = "Your Designia Data Export is Ready"

    # Try HTML template first, fallback to plain text
    try:
        html_message = render_to_string("authentication/emails/data_export_ready.html", context)
    except Exception:
        html_message = None

    text_message = f"""Hello {user.first_name or user.username},

Your data export is ready for download.

Download Link: {download_url}

This link will expire in 24 hours. Please download your data before then.

What's included in your export:
- Account information
- Profile data
- Order history
- Reviews you've written
- Messages
- Seller information (if applicable)

If you did not request this export, please contact our support team immediately.

Best regards,
The Designia Team
"""

    ok, info = send_email(
        subject=subject,
        message=text_message,
        recipient_list=[user.email],
        html_message=html_message,
    )

    if ok:
        logger.info(f"Export ready email sent to {user.email}")
    else:
        logger.error(f"Failed to send export ready email to {user.email}: {info}")


def _send_export_failure_email(user):
    """Send email notifying user that export failed."""
    subject = "Data Export Request Failed - Designia"

    text_message = f"""Hello {user.first_name or user.username},

We encountered an issue while processing your data export request.

Please try again later, or contact our support team if the problem persists.

We apologize for any inconvenience.

Best regards,
The Designia Team
"""

    ok, info = send_email(
        subject=subject,
        message=text_message,
        recipient_list=[user.email],
    )

    if ok:
        logger.info(f"Export failure email sent to {user.email}")
    else:
        logger.error(f"Failed to send export failure email to {user.email}: {info}")
