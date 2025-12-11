"""
ProfileService - Profile Management Business Logic.

Extracts all profile management logic from views into a testable,
reusable service layer. Handles profile updates, profile picture uploads/deletes.
"""

import logging
from typing import Any, Dict, Optional

from django.core.files.uploadedfile import UploadedFile

from authentication.domain.events import EventDispatcher
from authentication.infra.storage import StorageProvider
from utils.rbac import is_admin

from .results import Result


logger = logging.getLogger(__name__)


class ProfileService:
    """
    Profile management service encapsulating profile business logic.

    Handles profile updates with permission checks and profile picture operations.
    """

    def __init__(self, storage_provider: StorageProvider):
        """
        Initialize ProfileService with injected dependencies.

        Args:
            storage_provider: Storage provider for profile pictures
        """
        self.storage_provider = storage_provider

    def update_profile(self, user, profile_data: Dict[str, Any]) -> Result:
        """
        Update user profile with permission checks.

        Business Logic (extracted from ProfileUpdateView.update):
        1. Check if user is trying to update restricted fields
        2. Restricted fields only accessible to verified sellers OR admins
        3. Update profile fields
        4. Recalculate profile completion percentage

        Restricted fields:
        - phone_number, country_code, website, location
        - job_title, company, account_type
        - instagram_url, twitter_url, linkedin_url, facebook_url

        Args:
            user: CustomUser instance
            profile_data: Dict with profile field updates

        Returns:
            Result with update status
        """
        try:
            # Define restricted fields
            restricted_fields = [
                "website",
                "location",
                "job_title",
                "company",
                "account_type",
                "instagram_url",
                "twitter_url",
                "linkedin_url",
                "facebook_url",
            ]

            # Check permissions for restricted fields
            has_admin_privileges = is_admin(user)
            is_verified_seller = user.profile.is_verified_seller if hasattr(user, "profile") else False

            if not (is_verified_seller or has_admin_privileges):
                # Check if any restricted fields are being updated
                restricted_updates = [field for field in restricted_fields if field in profile_data]

                if restricted_updates:
                    logger.warning(f"User {user.id} attempted to update restricted fields: {restricted_updates}")
                    return Result(
                        success=False,
                        message="Professional, contact, and social media fields can only be updated by verified sellers.",
                        error="Access denied",
                        data={"restricted_fields": restricted_updates},
                    )

            # Update profile fields
            profile = user.profile
            updated_fields = []

            for field, value in profile_data.items():
                if hasattr(profile, field):
                    setattr(profile, field, value)
                    updated_fields.append(field)
                else:
                    logger.warning(f"Attempted to update non-existent profile field: {field}")

            # Save profile (this triggers profile completion calculation)
            profile.save()

            logger.info(f"Profile updated for user {user.id}. Updated fields: {updated_fields}")

            # Dispatch event
            EventDispatcher.dispatch_profile_updated(
                user=user, updated_fields=updated_fields, profile_completion=profile.profile_completion_percentage
            )

            return Result(
                success=True,
                message="Profile updated successfully.",
                data={
                    "updated_fields": updated_fields,
                    "profile_completion": profile.profile_completion_percentage,
                },
            )

        except Exception as e:
            logger.exception(f"Profile update error for user {user.id}: {e}")
            return Result(success=False, message="Failed to update profile.", error=str(e))

    def upload_profile_picture(self, user, image_file: UploadedFile) -> Result:
        """
        Upload profile picture to S3.

        Business Logic:
        1. Validate image file (size, type)
        2. Upload to S3 via storage provider
        3. Update profile.profile_picture_url with S3 key
        4. Generate temporary URL for response

        Args:
            user: CustomUser instance
            image_file: Django UploadedFile

        Returns:
            Result with upload status and temporary URL
        """
        try:
            # Validate file size
            max_size = 10 * 1024 * 1024  # 10MB
            if image_file.size > max_size:
                return Result(
                    success=False,
                    message=f"Image file too large. Maximum size is {max_size // (1024 * 1024)}MB",
                    error="File too large",
                )

            # Validate file type
            allowed_types = ["image/jpeg", "image/jpg", "image/png", "image/webp"]
            if hasattr(image_file, "content_type") and image_file.content_type not in allowed_types:
                return Result(
                    success=False,
                    message=f"Invalid file type. Allowed types: {', '.join(allowed_types)}",
                    error="Invalid file type",
                )

            # Generate S3 key
            file_extension = image_file.name.split(".")[-1] if "." in image_file.name else "jpg"
            s3_key = f"profile_pictures/{user.id}/profile.{file_extension}"

            # Delete old profile picture if exists
            profile = user.profile
            if profile.profile_picture_url:
                self.storage_provider.delete_file(profile.profile_picture_url)

            # Upload to S3
            success, file_key_or_error, upload_info = self.storage_provider.upload_file(
                file=image_file,
                path=s3_key,
                public=False,
                validate_image=True,  # Private profile pictures
            )

            if not success:
                return Result(success=False, message="Failed to upload profile picture.", error=file_key_or_error)

            # Update profile with S3 key
            profile.profile_picture_url = s3_key
            profile.save()

            # Generate temporary URL
            temp_url = self.get_profile_picture_url(user)

            logger.info(f"Profile picture uploaded for user {user.id}: {s3_key}")

            # Dispatch event
            EventDispatcher.dispatch_profile_picture_uploaded(user=user, file_key=s3_key)

            return Result(
                success=True,
                message="Profile picture uploaded successfully.",
                data={
                    "profile_picture_url": s3_key,
                    "profile_picture_temp_url": temp_url,
                    "size": upload_info.get("size") if upload_info else image_file.size,
                    "content_type": image_file.content_type,
                },
            )

        except Exception as e:
            logger.exception(f"Profile picture upload error for user {user.id}: {e}")
            return Result(success=False, message="Failed to upload profile picture.", error=str(e))

    def delete_profile_picture(self, user) -> Result:
        """
        Delete profile picture from S3.

        Business Logic:
        1. Check if profile picture exists
        2. Delete from S3 via storage provider
        3. Clear profile.profile_picture_url

        Args:
            user: CustomUser instance

        Returns:
            Result with deletion status
        """
        try:
            profile = user.profile

            if not profile.profile_picture_url:
                return Result(success=False, message="No profile picture to delete.", error="No profile picture")

            # Delete from S3
            success, message = self.storage_provider.delete_file(profile.profile_picture_url)

            if not success:
                return Result(success=False, message="Failed to delete profile picture from storage.", error=message)

            # Clear profile picture URL from database
            profile.profile_picture_url = None
            profile.save()

            logger.info(f"Profile picture deleted for user {user.id}")

            # Dispatch event
            EventDispatcher.dispatch_profile_picture_deleted(user=user)

            return Result(success=True, message="Profile picture deleted successfully.")

        except Exception as e:
            logger.exception(f"Profile picture deletion error for user {user.id}: {e}")
            return Result(success=False, message="Failed to delete profile picture.", error=str(e))

    def get_profile_picture_url(self, user, expires_in: int = 3600) -> Optional[str]:
        """
        Get temporary signed URL for profile picture.

        Delegates to Profile.get_profile_picture_temp_url() which uses
        storage provider internally.

        Args:
            user: CustomUser instance
            expires_in: URL expiration time in seconds (default: 3600 = 1 hour)

        Returns:
            Temporary signed URL or None if no profile picture
        """
        try:
            profile = user.profile
            if not profile.profile_picture_url:
                return None

            # Use storage provider to generate URL
            return self.storage_provider.get_file_url(profile.profile_picture_url, expires_in=expires_in)

        except Exception as e:
            logger.warning(f"Failed to generate profile picture URL for user {user.id}: {e}")
            return None
