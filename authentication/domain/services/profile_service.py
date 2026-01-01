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

    def delete_user_account(self, user) -> Result:
        """
        Delete user account (GDPR Right to Erasure).

        Business Logic:
        1. Delete profile picture from storage
        2. Delete seller's products and associated images from S3
        3. Delete user's favorites
        4. Delete user's cart
        5. Anonymize public data (reviews) - set reviewer to NULL, store "Deleted User" name
        6. Delete private data (chat messages and chats)
        7. Delete review helpful votes
        8. Delete return requests
        9. Delete activity tracking data
        10. Clear personal profile data
        11. Deactivate and anonymize user account
        12. Dispatch account deleted event
        Note: Password already verified in view layer

        Args:
            user: CustomUser instance to delete

        Returns:
            Result with deletion status
        """
        from django.db import transaction

        try:
            with transaction.atomic():
                user_id = str(user.id)
                user_email = user.email

                # 1. Delete profile picture if exists
                if hasattr(user, "profile") and user.profile.profile_picture_url:
                    self.storage_provider.delete_file(user.profile.profile_picture_url)

                # 2. Delete seller's products and associated images from S3
                try:
                    from marketplace.catalog.domain.models import Product, ProductImage

                    # Get all products by this seller
                    seller_products = Product.objects.filter(seller=user)

                    # Delete product images from S3 storage
                    for product in seller_products:
                        product_images = ProductImage.objects.filter(product=product)
                        for image in product_images:
                            # Delete from S3 if s3_key exists
                            if image.s3_key:
                                try:
                                    self.storage_provider.delete_file(image.s3_key)
                                except Exception as img_e:
                                    logger.warning(f"Failed to delete product image {image.id} from S3: {img_e}")

                    # Delete all products (CASCADE will delete ProductImages, reviews, etc.)
                    products_count = seller_products.count()
                    seller_products.delete()
                    logger.info(f"Deleted {products_count} products for user {user_id}")

                except (ImportError, Exception) as e:
                    logger.info(f"Could not delete products for user {user_id}: {e}")

                # 3. Delete user's favorites
                try:
                    from marketplace.catalog.domain.models import ProductFavorite

                    favorites_deleted = ProductFavorite.objects.filter(user=user).delete()[0]
                    logger.info(f"Deleted {favorites_deleted} favorites for user {user_id}")
                except (ImportError, Exception) as e:
                    logger.info(f"Could not delete favorites for user {user_id}: {e}")

                # 4. Delete user's cart
                try:
                    from marketplace.cart.domain.models import Cart

                    Cart.objects.filter(user=user).delete()
                    logger.info(f"Deleted cart for user {user_id}")
                except (ImportError, Exception) as e:
                    logger.info(f"Could not delete cart for user {user_id}: {e}")

                # 5. Anonymize reviews written by this user (if marketplace app exists)
                try:
                    from marketplace.models import ProductReview

                    reviews_count = ProductReview.objects.filter(reviewer=user).update(
                        reviewer=None,
                        reviewer_name="Deleted User",
                    )
                    logger.info(f"Anonymized {reviews_count} reviews for user {user_id}")
                except (ImportError, Exception) as e:
                    logger.info(f"Could not anonymize reviews for user {user_id}: {e}")

                # 6. Delete chat messages and chats (if chat app exists)
                try:
                    from chat.models import Chat, Message

                    messages_deleted = Message.objects.filter(sender=user).delete()[0]
                    logger.info(f"Deleted {messages_deleted} messages for user {user_id}")

                    # Delete chats where user is participant
                    from django.db.models import Q

                    chats_deleted = Chat.objects.filter(Q(user1=user) | Q(user2=user)).delete()[0]
                    logger.info(f"Deleted {chats_deleted} chats for user {user_id}")
                except (ImportError, Exception) as e:
                    logger.info(f"Could not delete messages/chats for user {user_id}: {e}")

                # 7. Delete review helpful votes
                try:
                    from marketplace.models import ProductReviewHelpful

                    helpful_deleted = ProductReviewHelpful.objects.filter(user=user).delete()[0]
                    logger.info(f"Deleted {helpful_deleted} helpful votes for user {user_id}")
                except (ImportError, Exception) as e:
                    logger.info(f"Could not delete helpful votes for user {user_id}: {e}")

                # 8. Delete return requests
                try:
                    from marketplace.ordering.domain.models import ReturnRequest

                    returns_deleted = ReturnRequest.objects.filter(requested_by=user).delete()[0]
                    logger.info(f"Deleted {returns_deleted} return requests for user {user_id}")
                except (ImportError, Exception) as e:
                    logger.info(f"Could not delete return requests for user {user_id}: {e}")

                # 9. Delete user activity tracking data
                try:
                    from activity.models import UserClick

                    activity_deleted = UserClick.objects.filter(user=user).delete()[0]
                    logger.info(f"Deleted {activity_deleted} activity records for user {user_id}")
                except (ImportError, Exception) as e:
                    logger.info(f"Could not delete activity records for user {user_id}: {e}")

                # 10. Clear personal profile data
                if hasattr(user, "profile"):
                    profile = user.profile
                    profile.bio = ""
                    profile.phone_number = ""
                    profile.website = ""
                    profile.location = ""
                    profile.street_address = ""
                    profile.city = ""
                    profile.state_province = ""
                    profile.country = ""
                    profile.postal_code = ""
                    profile.instagram_url = ""
                    profile.twitter_url = ""
                    profile.linkedin_url = ""
                    profile.facebook_url = ""
                    profile.profile_picture_url = None
                    profile.save()

                # 11. Anonymize and deactivate user
                user.email = f"deleted_{user_id}@deleted.local"
                user.username = f"deleted_{user_id}"
                user.first_name = "Deleted"
                user.last_name = "User"
                user.is_active = False
                user.set_unusable_password()
                user.save()

                # 12. Dispatch event for any cleanup handlers
                EventDispatcher.dispatch_account_deleted(user_id=user_id, email=user_email)

                logger.info(f"Account deleted for user {user_id}")

                return Result(
                    success=True,
                    message="Account deleted successfully.",
                    data={"user_id": user_id},
                )

        except Exception as e:
            logger.exception(f"Account deletion error for user {user.id}: {e}")
            return Result(success=False, message="Failed to delete account.", error=str(e))

    def collect_user_data(self, user) -> Dict[str, Any]:
        """
        Collect all user data for GDPR export.

        Collects data from all related models and returns a dictionary
        suitable for JSON export.

        Args:
            user: CustomUser instance

        Returns:
            Dict containing all user data
        """
        from django.utils import timezone

        data = {
            "export_date": timezone.now().isoformat(),
            "user_id": str(user.id),
            "account": {
                "email": user.email,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "date_joined": user.date_joined.isoformat() if user.date_joined else None,
                "last_login": user.last_login.isoformat() if user.last_login else None,
                "is_active": user.is_active,
                "role": user.role if hasattr(user, "role") else None,
            },
            "profile": {},
            "orders": [],
            "reviews": [],
            "messages": [],
            "seller_data": None,
        }

        # Profile data
        if hasattr(user, "profile"):
            profile = user.profile
            data["profile"] = {
                "bio": profile.bio,
                "location": profile.location,
                "phone_number": profile.phone_number,
                "country_code": profile.country_code if hasattr(profile, "country_code") else None,
                "website": profile.website,
                "job_title": profile.job_title if hasattr(profile, "job_title") else None,
                "company": profile.company if hasattr(profile, "company") else None,
                "birth_date": str(profile.birth_date)
                if hasattr(profile, "birth_date") and profile.birth_date
                else None,
                "gender": profile.gender if hasattr(profile, "gender") else None,
                "timezone": str(profile.timezone) if hasattr(profile, "timezone") else None,
                "language_preference": profile.language_preference
                if hasattr(profile, "language_preference")
                else None,
                "currency_preference": profile.currency_preference
                if hasattr(profile, "currency_preference")
                else None,
                "is_verified_seller": profile.is_verified_seller if hasattr(profile, "is_verified_seller") else False,
                "seller_type": profile.seller_type if hasattr(profile, "seller_type") else None,
                "marketing_emails_enabled": profile.marketing_emails_enabled
                if hasattr(profile, "marketing_emails_enabled")
                else None,
                "newsletter_enabled": profile.newsletter_enabled if hasattr(profile, "newsletter_enabled") else None,
            }

        # Orders (if marketplace exists)
        try:
            from marketplace.models import Order

            orders = Order.objects.filter(buyer=user).select_related("seller")
            data["orders"] = [
                {
                    "id": str(order.id),
                    "created_at": order.created_at.isoformat() if order.created_at else None,
                    "status": order.status,
                    "total_amount": str(order.total_amount) if hasattr(order, "total_amount") else None,
                }
                for order in orders
            ]
        except (ImportError, Exception) as e:
            logger.info(f"Could not collect orders for user {user.id}: {e}")

        # Reviews (if marketplace exists)
        try:
            from marketplace.models import ProductReview

            reviews = ProductReview.objects.filter(reviewer=user)
            data["reviews"] = [
                {
                    "id": str(review.id),
                    "created_at": review.created_at.isoformat() if review.created_at else None,
                    "rating": review.rating,
                    "title": review.title,
                    "comment": review.comment,
                    "product_id": str(review.product_id) if review.product_id else None,
                }
                for review in reviews
            ]
        except (ImportError, Exception) as e:
            logger.info(f"Could not collect reviews for user {user.id}: {e}")

        # Messages (if chat exists)
        try:
            from chat.models import Message

            messages = Message.objects.filter(sender=user).order_by("-created_at")[:100]
            data["messages"] = [
                {
                    "id": str(msg.id),
                    "created_at": msg.created_at.isoformat() if msg.created_at else None,
                    "content": msg.content[:200] + "..." if len(msg.content) > 200 else msg.content,
                }
                for msg in messages
            ]
        except (ImportError, Exception) as e:
            logger.info(f"Could not collect messages for user {user.id}: {e}")

        # Seller data (if applicable)
        try:
            from authentication.domain.models import SellerApplication

            seller_app = SellerApplication.objects.filter(user=user).first()
            if seller_app:
                data["seller_data"] = {
                    "business_name": seller_app.business_name if hasattr(seller_app, "business_name") else None,
                    "status": seller_app.status,
                    "created_at": seller_app.created_at.isoformat() if seller_app.created_at else None,
                }
        except (ImportError, Exception) as e:
            logger.info(f"Could not collect seller data for user {user.id}: {e}")

        return data
