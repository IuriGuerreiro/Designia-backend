"""
SellerService - Seller Application Business Logic.

Extracts all seller application workflow logic from views into a testable,
reusable service layer. Handles submission, approval, rejection, and status queries.
"""

import logging
from typing import Any, Dict, List

from django.db import transaction
from django.utils import timezone

from authentication.domain.events import EventDispatcher
from authentication.infra.storage import StorageProvider
from authentication.models import SellerApplication, SellerApplicationImage
from utils.rbac import is_seller

from .results import Result


logger = logging.getLogger(__name__)


class SellerService:
    """
    Seller application service encapsulating seller workflow business logic.

    Handles application submission, approval/rejection, and status queries.
    """

    def __init__(self, storage_provider: StorageProvider):
        """
        Initialize SellerService with injected dependencies.

        Args:
            storage_provider: Storage provider for workshop images
        """
        self.storage_provider = storage_provider

    @transaction.atomic
    def submit_application(self, user, application_data: Dict[str, Any], workshop_photos: List[Any]) -> Result:
        """
        Submit new seller application or resubmit rejected one.

        Business Logic:
        1. Check for existing in-progress applications
        2. Check if user is already a seller
        3. Verify 2FA is enabled
        4. Create or update application
        5. Upload workshop images via storage provider
        6. Transaction management (rollback on any failure)

        Args:
            user: CustomUser instance
            application_data: Dict with:
                - business_name: str
                - seller_type: str (manufacturer, designer, etc.)
                - motivation: str
                - portfolio_url: str
                - social_media_url: str (optional)
            workshop_photos: List of Django UploadedFile objects

        Returns:
            Result with success status and application_id
        """
        try:
            # 1. Check for existing in-progress applications
            existing = SellerApplication.objects.filter(user=user).order_by("-submitted_at").first()

            if existing and existing.status in ["pending", "under_review", "revision_requested"]:
                return Result(
                    success=False,
                    message="You already have a seller application in progress.",
                    error="Application already exists",
                )

            # 2. Check if user is already a seller
            if is_seller(user):
                return Result(
                    success=False, message="You are already a verified seller.", error="User is already a seller"
                )

            # 3. Check 2FA requirement
            if not user.two_factor_enabled:
                return Result(
                    success=False,
                    message="Two-factor authentication (2FA) must be enabled before applying to become a seller. Please enable 2FA in your settings.",
                    error="2FA not enabled",
                )

            # 4. Create or resubmit application
            if existing and existing.status == "rejected":
                # Resubmit previously rejected application
                return self._resubmit_application(existing, application_data, workshop_photos)
            else:
                # Create new application
                return self._create_new_application(user, application_data, workshop_photos)

        except Exception as e:
            logger.exception(f"Seller application submission error for user {user.id}: {e}")
            return Result(success=False, message=f"Failed to submit application: {str(e)}", error=str(e))

    def _create_new_application(self, user, application_data: Dict[str, Any], workshop_photos: List[Any]) -> Result:
        """Create a new seller application."""
        try:
            # Create application
            application = SellerApplication.objects.create(
                user=user,
                business_name=application_data.get("business_name"),
                seller_type=application_data.get("seller_type"),
                motivation=application_data.get("motivation"),
                portfolio_url=application_data.get("portfolio_url"),
                social_media_url=application_data.get("social_media_url", ""),
                status="pending",
            )

            # Upload workshop images
            upload_result = self._upload_workshop_images(application, workshop_photos)
            if not upload_result.success:
                # Rollback transaction if image upload fails
                raise Exception(upload_result.error)

            logger.info(f"Seller application created: {application.id} for user {user.id}")

            # Dispatch event
            EventDispatcher.dispatch_seller_application_submitted(application=application, is_resubmission=False)

            return Result(
                success=True,
                message="Seller application submitted successfully!",
                data={
                    "application_id": application.id,
                    "images_uploaded": upload_result.data.get("images_uploaded", 0),
                },
            )

        except Exception as e:
            logger.error(f"Failed to create seller application: {e}")
            raise  # Re-raise to trigger transaction rollback

    def _resubmit_application(
        self, existing: SellerApplication, application_data: Dict[str, Any], workshop_photos: List[Any]
    ) -> Result:
        """Resubmit a previously rejected application."""
        try:
            # Update application fields
            existing.business_name = application_data.get("business_name")
            existing.seller_type = application_data.get("seller_type")
            existing.motivation = application_data.get("motivation")
            existing.portfolio_url = application_data.get("portfolio_url")
            existing.social_media_url = application_data.get("social_media_url", "")
            existing.status = "pending"
            existing.admin_notes = ""
            existing.rejection_reason = ""
            existing.reviewed_at = None
            existing.approved_by = None
            existing.rejected_by = None
            existing.submitted_at = timezone.now()
            existing.save()

            # Delete old images and upload new ones
            existing.images.all().delete()
            upload_result = self._upload_workshop_images(existing, workshop_photos)
            if not upload_result.success:
                raise Exception(upload_result.error)

            logger.info(f"Seller application resubmitted: {existing.id} for user {existing.user.id}")

            # Dispatch event
            EventDispatcher.dispatch_seller_application_submitted(application=existing, is_resubmission=True)

            return Result(
                success=True,
                message="Seller application resubmitted successfully!",
                data={"application_id": existing.id, "images_uploaded": upload_result.data.get("images_uploaded", 0)},
            )

        except Exception as e:
            logger.error(f"Failed to resubmit seller application: {e}")
            raise  # Re-raise to trigger transaction rollback

    def _upload_workshop_images(self, application: SellerApplication, workshop_photos: List[Any]) -> Result:
        """
        Upload workshop images for seller application.

        Uses StorageProvider to abstract S3/local storage.
        """
        try:
            images_uploaded = 0

            for index, image_file in enumerate(workshop_photos):
                # Generate storage path
                storage_path = f"seller_applications/{application.id}/workshop_{index}_{image_file.name}"

                # Upload via storage provider
                success, file_key_or_error, upload_info = self.storage_provider.upload_file(
                    file=image_file, path=storage_path, public=False, validate_image=True
                )

                if not success:
                    logger.error(
                        f"Failed to upload image {index} for application {application.id}: {file_key_or_error}"
                    )
                    return Result(success=False, message="Failed to upload workshop images.", error=file_key_or_error)

                # Create SellerApplicationImage record
                # We set the image name directly to the path returned by storage provider
                # This prevents Django from attempting to upload/save the file a second time
                image_record = SellerApplicationImage(
                    application=application,
                    image_type="workshop",
                    description=f"Workshop photo {index + 1}",
                    order=index,
                )
                image_record.image.name = file_key_or_error
                image_record.save()

                images_uploaded += 1

            return Result(
                success=True,
                message=f"Uploaded {images_uploaded} workshop images.",
                data={"images_uploaded": images_uploaded},
            )

        except Exception as e:
            logger.exception(f"Image upload error for application {application.id}: {e}")
            return Result(success=False, message="Failed to upload images.", error=str(e))

    @transaction.atomic
    def approve_application(self, application_id: int, admin_user) -> Result:
        """
        Approve seller application and upgrade user to seller role.

        Business Logic (extracted from SellerApplication.approve_application):
        1. Update application status
        2. Upgrade user role to 'seller'
        3. Update profile (is_verified_seller=True, seller_type)
        4. Record admin who approved

        Args:
            application_id: SellerApplication ID
            admin_user: Admin user performing approval

        Returns:
            Result with approval status
        """
        try:
            # Get application
            try:
                application = SellerApplication.objects.get(id=application_id)
            except SellerApplication.DoesNotExist:
                return Result(success=False, message="Application not found.", error="Application not found")

            # Update application status
            application.status = "approved"
            application.reviewed_at = timezone.now()
            application.approved_by = admin_user
            application.save()

            # Upgrade user to seller role
            user = application.user
            user.role = "seller"
            user.save()

            # Update profile
            profile = user.profile
            profile.is_verified_seller = True
            profile.seller_type = application.seller_type
            profile.save()

            logger.info(
                f"Seller application {application_id} approved by admin {admin_user.id}. "
                f"User {user.id} upgraded to seller."
            )

            # Dispatch event
            EventDispatcher.dispatch_seller_application_approved(application=application, admin_user=admin_user)

            return Result(
                success=True,
                message=f"Seller application approved for {user.email}",
                data={
                    "application_id": application.id,
                    "user_id": str(user.id),
                    "user_email": user.email,
                },
            )

        except Exception as e:
            logger.exception(f"Seller approval error for application {application_id}: {e}")
            return Result(success=False, message=f"Failed to approve application: {str(e)}", error=str(e))

    @transaction.atomic
    def reject_application(self, application_id: int, admin_user, reason: str) -> Result:
        """
        Reject seller application with reason.

        Business Logic (extracted from SellerApplication.reject_application):
        1. Update application status to 'rejected'
        2. Record rejection reason
        3. Record admin who rejected

        Args:
            application_id: SellerApplication ID
            admin_user: Admin user performing rejection
            reason: Rejection reason

        Returns:
            Result with rejection status
        """
        try:
            # Get application
            try:
                application = SellerApplication.objects.get(id=application_id)
            except SellerApplication.DoesNotExist:
                return Result(success=False, message="Application not found.", error="Application not found")

            # Update application status
            application.status = "rejected"
            application.reviewed_at = timezone.now()
            application.rejected_by = admin_user
            application.rejection_reason = reason
            application.save()

            logger.info(f"Seller application {application_id} rejected by admin {admin_user.id}. Reason: {reason}")

            # Dispatch event
            EventDispatcher.dispatch_seller_application_rejected(
                application=application, admin_user=admin_user, reason=reason
            )

            return Result(
                success=True,
                message=f"Seller application rejected for {application.user.email}",
                data={
                    "application_id": application.id,
                    "user_id": str(application.user.id),
                    "user_email": application.user.email,
                    "reason": reason,
                },
            )

        except Exception as e:
            logger.exception(f"Seller rejection error for application {application_id}: {e}")
            return Result(success=False, message=f"Failed to reject application: {str(e)}", error=str(e))

    def get_application_status(self, user) -> Dict[str, Any]:
        """
        Get user's seller application status.

        Returns most recent application if exists.

        Args:
            user: CustomUser instance

        Returns:
            Dict with application status information
        """
        try:
            application = SellerApplication.objects.filter(user=user).order_by("-submitted_at").first()

            if application:
                return {
                    "has_application": True,
                    "is_seller": is_seller(user),
                    "status": application.status,
                    "application_id": application.id,
                    "submitted_at": application.submitted_at,
                    "admin_notes": application.admin_notes,
                    "rejection_reason": application.rejection_reason,
                }

            return {
                "has_application": False,
                "is_seller": is_seller(user),
                "status": None,
            }

        except Exception as e:
            logger.exception(f"Error getting application status for user {user.id}: {e}")
            return {
                "has_application": False,
                "is_seller": False,
                "status": None,
                "error": str(e),
            }
