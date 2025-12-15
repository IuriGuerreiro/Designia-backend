"""
Stripe Connect service for seller account management.
Handles Stripe account creation, validation, and session management for sellers.
Refactored to use PaymentProvider interface.
"""

import logging

from django.contrib.auth import get_user_model

from payment_system.infra.payment_provider.stripe_provider import StripePaymentProvider


logger = logging.getLogger(__name__)

User = get_user_model()


class StripeConnectService:
    """Service class for managing Stripe Connect accounts for sellers."""

    _provider = None

    @classmethod
    def get_provider(cls):
        if cls._provider is None:
            cls._provider = StripePaymentProvider()
        return cls._provider

    @staticmethod
    def validate_seller_requirements(user):
        """
        Validate that user meets requirements to create a Stripe account.

        Requirements:
        1. For regular users: Must have password and 2FA enabled
        2. For OAuth users: No additional requirements (they use Google/social auth)
        3. User must not already have a Stripe account

        Args:
            user (CustomUser): The user to validate

        Returns:
            dict: Validation result with success status and errors
        """
        logger.info(f"🔍 VALIDATING SELLER REQUIREMENTS for user: {user.email}")
        logger.debug(
            f"📋 User info: is_oauth={user.is_oauth_only_user()}, has_stripe_account={bool(user.stripe_account_id)}, two_factor_enabled={getattr(user, 'two_factor_enabled', 'N/A')}"
        )

        errors = []

        # Check if user already has a Stripe account
        if user.stripe_account_id:
            logger.info(f" User already has Stripe account: {user.stripe_account_id}")
            errors.append("User already has a Stripe account associated with this profile.")
        else:
            logger.info("  User does not have existing Stripe account")

        # For non-OAuth users, require password and 2FA
        if not user.is_oauth_only_user():
            logger.info("🔍 Checking regular user requirements (password + 2FA)...")

            # Check if user has usable password
            has_password = user.has_usable_password()
            logger.info(f"🔑 Has usable password: {has_password}")

            if not has_password:
                logger.warning(" User doesn't have usable password")
                errors.append("Password is required to create a seller account. Please set up a password first.")
            else:
                # Additional check for passwords starting with '!' (Django's unusable password prefix)
                if hasattr(user, "password") and user.password and user.password.startswith("!"):
                    logger.warning(" User has invalid password (starts with '!')")
                    errors.append("Invalid password detected. Please reset your password to continue.")
                else:
                    logger.info("  User has valid password")

            # Check if 2FA is enabled for non-OAuth users
            two_factor_enabled = getattr(user, "two_factor_enabled", False)
            logger.info(f"🔐 Two-factor enabled: {two_factor_enabled}")

            if not two_factor_enabled:
                logger.warning(" User doesn't have 2FA enabled")
                errors.append("Two-factor authentication must be enabled to create a seller account.")
            else:
                logger.info("  User has 2FA enabled")
        else:
            logger.info("  OAuth user - no additional password/2FA requirements")

        result = {"valid": len(errors) == 0, "errors": errors}

        logger.info(f"📊 VALIDATION RESULT: {result}")
        return result

    @staticmethod
    def validate_seller_session_requirements(user):
        """
        Validate that user meets requirements for account session creation.
        Similar to validate_seller_requirements but allows existing accounts.

        Requirements:
        1. For regular users: Must have password and 2FA enabled
        2. For OAuth users: No additional requirements (they use Google/social auth)

        Args:
            user (CustomUser): The user to validate

        Returns:
            dict: Validation result with success status and errors
        """
        logger.info(f"🔍 VALIDATING SESSION REQUIREMENTS for user: {user.email}")
        logger.debug(
            f"📋 User info: is_oauth={user.is_oauth_only_user()}, has_stripe_account={bool(user.stripe_account_id)}, two_factor_enabled={getattr(user, 'two_factor_enabled', 'N/A')}"
        )

        errors = []

        # For non-OAuth users, require password and 2FA
        if not user.is_oauth_only_user():
            logger.info("🔍 Checking regular user session requirements (password + 2FA)...")

            # Check if user has usable password
            has_password = user.has_usable_password()
            logger.info(f"🔑 Has usable password: {has_password}")

            if not has_password:
                logger.warning(" User doesn't have usable password")
                errors.append("Password is required to access seller account. Please set up a password first.")
            else:
                # Additional check for passwords starting with '!' (Django's unusable password prefix)
                if hasattr(user, "password") and user.password and user.password.startswith("!"):
                    logger.warning(" User has invalid password (starts with '!')")
                    errors.append("Invalid password detected. Please reset your password to continue.")
                else:
                    logger.info("  User has valid password")

            # Check if 2FA is enabled for non-OAuth users
            two_factor_enabled = getattr(user, "two_factor_enabled", False)
            logger.info(f"🔐 Two-factor enabled: {two_factor_enabled}")

            if not two_factor_enabled:
                logger.warning(" User doesn't have 2FA enabled")
                errors.append("Two-factor authentication must be enabled to access seller account.")
            else:
                logger.info("  User has 2FA enabled")
        else:
            logger.info("  OAuth user - no additional password/2FA requirements for session")

        result = {"valid": len(errors) == 0, "errors": errors}

        logger.info(f"📊 SESSION VALIDATION RESULT: {result}")
        return result

    @classmethod
    def create_stripe_account(cls, user, country="US", business_type="individual"):
        """
        Create a Stripe Express account for the seller.

        Args:
            user (CustomUser): The user to create account for
            country (str): Country code for the account
            business_type (str): Type of business account ('individual' or 'company')

        Returns:
            dict: Result with account_id and success status
        """
        logger.info(f"🔄 STRIPE ACCOUNT CREATION START for user: {user.email}")
        logger.info(f"📋 Request parameters: country={country}, business_type={business_type}")
        try:
            # First validate user requirements
            logger.info("🔍 Validating user requirements...")
            validation = cls.validate_seller_requirements(user)
            logger.info(f"  Validation result: {validation}")

            if not validation["valid"]:
                logger.warning(f" Validation failed with errors: {validation['errors']}")
                return {"success": False, "errors": validation["errors"]}

            logger.info("  User validation passed, creating Stripe account...")

            # Use provider to create account
            provider = cls.get_provider()

            # Prepare kwargs for individual info if needed
            kwargs = {}
            if business_type == "individual":
                kwargs["first_name"] = user.first_name or ""
                kwargs["last_name"] = user.last_name or ""

            logger.info("🚀 Calling PaymentProvider.create_connected_account...")
            account = provider.create_connected_account(
                email=user.email, country=country, business_type=business_type, **kwargs
            )

            logger.info("  Stripe account created successfully!")
            logger.info(f"🆔 Account ID: {account.id}")
            logger.info(
                f"📊 Account status: charges_enabled={account.charges_enabled}, details_submitted={account.details_submitted}"
            )

            # Save account ID to user model
            logger.info("💾 Saving account ID to user model...")
            user.stripe_account_id = account.id
            user.save(update_fields=["stripe_account_id"])

            logger.info(f"  Account ID saved to user {user.email}")
            logger.info(f"Created Stripe account {account.id} for user {user.email}")

            return {"success": True, "account_id": account.id, "account": account}

        except Exception as e:
            logger.exception(f" UNEXPECTED ERROR creating Stripe account for user {user.email}: {str(e)}")
            logger.error(f"Unexpected error creating Stripe account for user {user.email}: {str(e)}")
            return {"success": False, "errors": [f"An unexpected error occurred: {str(e)}"]}

    @classmethod
    def create_account_session(cls, user):
        """
        Create an Account Session for seller onboarding using Stripe Connect JS.

        Args:
            user (CustomUser): The user with Stripe account

        Returns:
            dict: Result with account session data
        """
        logger.info(f"🔄 STRIPE ACCOUNT SESSION CREATION START for user: {user.email}")
        logger.info(f"🆔 User's Stripe Account ID: {user.stripe_account_id}")
        try:
            # Validate user requirements for session access (allows existing accounts)
            logger.info("🔍 Validating user session requirements...")
            validation = cls.validate_seller_session_requirements(user)
            logger.info(f"  Session validation result: {validation}")

            if not validation["valid"]:
                logger.warning(f" Session validation failed with errors: {validation['errors']}")
                return {"success": False, "errors": validation["errors"]}

            if not user.stripe_account_id:
                logger.warning(" User does not have a Stripe account ID")
                return {
                    "success": False,
                    "errors": ["User does not have a Stripe account. Please create an account first."],
                }

            logger.info("  User has valid Stripe account, creating account session...")

            provider = cls.get_provider()

            components = {
                "account_onboarding": {
                    "enabled": True,
                    "features": {"disable_stripe_user_authentication": True, "external_account_collection": True},
                }
            }
            settings_params = {"payouts": {"schedule": {"interval": "manual"}}}  # 🔑 disables automatic payouts

            logger.info("🚀 Calling PaymentProvider.create_account_session...")
            account_session = provider.create_account_session(
                account_id=user.stripe_account_id, components=components, settings=settings_params
            )

            logger.info("  Account session created successfully!")
            logger.debug(
                f"🔑 Client secret: {account_session.client_secret[:20]}...{account_session.client_secret[-10:] if len(account_session.client_secret) > 30 else account_session.client_secret}"
            )
            logger.info(f"⏰ Session expires at: {account_session.expires_at}")

            logger.info(f"Created account session for user {user.email} with account {user.stripe_account_id}")

            return {
                "success": True,
                "client_secret": account_session.client_secret,
                "account_id": user.stripe_account_id,
            }

        except Exception as e:
            logger.exception(f" UNEXPECTED ERROR in session creation for user {user.email}: {str(e)}")
            logger.error(f"Unexpected error creating account session for user {user.email}: {str(e)}")
            return {"success": False, "errors": [f"An unexpected error occurred: {str(e)}"]}

    @classmethod
    def get_account_status(cls, user):
        """
        Get the status of a user's Stripe account.

        Args:
            user (CustomUser): The user to check

        Returns:
            dict: Account status information
        """
        try:
            if not user.stripe_account_id:
                return {"success": True, "has_account": False, "status": "no_account"}

            provider = cls.get_provider()
            account = provider.retrieve_account(user.stripe_account_id)

            return {
                "success": True,
                "has_account": True,
                "account_id": account.id,
                "status": "active" if account.details_submitted and account.charges_enabled else "incomplete",
                "details_submitted": account.details_submitted,
                "charges_enabled": account.charges_enabled,
                "payouts_enabled": account.payouts_enabled,
                "requirements": account.requirements,
                "account_data": account,
            }

        except Exception as e:
            logger.error(f"Unexpected error getting account status for user {user.email}: {str(e)}")
            return {"success": False, "errors": [f"An unexpected error occurred: {str(e)}"]}

    @staticmethod
    def handle_account_updated_webhook(account_id, account_data):
        """
        Handle account.updated webhook from Stripe.
        Updates local user data when Stripe account is updated.

        Args:
            account_id (str): Stripe account ID
            account_data (dict): Account data from webhook

        Returns:
            dict: Processing result
        """
        try:
            # Find user with this Stripe account ID
            try:
                user = User.objects.get(stripe_account_id=account_id)
            except User.DoesNotExist:
                logger.warning(f"Received webhook for unknown Stripe account: {account_id}")
                return {"success": False, "errors": [f"No user found with Stripe account ID: {account_id}"]}

            # Update user's seller status if account is complete
            if account_data.get("details_submitted") and account_data.get("charges_enabled"):
                if hasattr(user, "profile"):
                    user.profile.is_verified_seller = True
                    user.profile.save(update_fields=["is_verified_seller"])
                    logger.info(f"Updated user {user.email} to verified seller status")

            logger.info(f"Processed account.updated webhook for user {user.email}")

            return {"success": True, "user_id": user.id, "account_id": account_id}

        except Exception as e:
            logger.error(f"Error processing account.updated webhook: {str(e)}")
            return {"success": False, "errors": [f"Failed to process webhook: {str(e)}"]}


def create_seller_account(user, country="US", business_type="individual"):
    """
    Convenience function to create a Stripe account for a seller.
    """
    return StripeConnectService.create_stripe_account(user, country, business_type)


def create_seller_account_session(user):
    """
    Convenience function to create an account session for seller onboarding.
    """
    return StripeConnectService.create_account_session(user)


def validate_seller_eligibility(user):
    """
    Convenience function to validate seller eligibility.
    """
    return StripeConnectService.validate_seller_requirements(user)
