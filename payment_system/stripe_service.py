"""
Stripe Connect service for seller account management.
Handles Stripe account creation, validation, and session management for sellers.
"""
import stripe
import logging
from django.conf import settings
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)

# Configure Stripe API key
stripe.api_key = getattr(settings, 'STRIPE_SECRET_KEY', '')

User = get_user_model()


class StripeConnectService:
    """Service class for managing Stripe Connect accounts for sellers."""
    
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
        print(f"🔍 VALIDATING SELLER REQUIREMENTS for user: {user.email}")
        print(f"📋 User info: is_oauth={user.is_oauth_only_user()}, has_stripe_account={bool(user.stripe_account_id)}, two_factor_enabled={getattr(user, 'two_factor_enabled', 'N/A')}")
        
        errors = []
        
        # Check if user already has a Stripe account
        if user.stripe_account_id:
            print(f"❌ User already has Stripe account: {user.stripe_account_id}")
            errors.append("User already has a Stripe account associated with this profile.")
        else:
            print("✅ User does not have existing Stripe account")
        
        # For non-OAuth users, require password and 2FA
        if not user.is_oauth_only_user():
            print("🔍 Checking regular user requirements (password + 2FA)...")
            
            # Check if user has usable password
            has_password = user.has_usable_password()
            print(f"🔑 Has usable password: {has_password}")
            
            if not has_password:
                print("❌ User doesn't have usable password")
                errors.append("Password is required to create a seller account. Please set up a password first.")
            else:
                # Additional check for passwords starting with '!' (Django's unusable password prefix)
                if hasattr(user, 'password') and user.password and user.password.startswith('!'):
                    print("❌ User has invalid password (starts with '!')")
                    errors.append("Invalid password detected. Please reset your password to continue.")
                else:
                    print("✅ User has valid password")
            
            # Check if 2FA is enabled for non-OAuth users
            two_factor_enabled = getattr(user, 'two_factor_enabled', False)
            print(f"🔐 Two-factor enabled: {two_factor_enabled}")
            
            if not two_factor_enabled:
                print("❌ User doesn't have 2FA enabled")
                errors.append("Two-factor authentication must be enabled to create a seller account.")
            else:
                print("✅ User has 2FA enabled")
        else:
            print("✅ OAuth user - no additional password/2FA requirements")
        
        result = {
            'valid': len(errors) == 0,
            'errors': errors
        }
        
        print(f"📊 VALIDATION RESULT: {result}")
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
        print(f"🔍 VALIDATING SESSION REQUIREMENTS for user: {user.email}")
        print(f"📋 User info: is_oauth={user.is_oauth_only_user()}, has_stripe_account={bool(user.stripe_account_id)}, two_factor_enabled={getattr(user, 'two_factor_enabled', 'N/A')}")
        
        errors = []
        
        # For non-OAuth users, require password and 2FA
        if not user.is_oauth_only_user():
            print("🔍 Checking regular user session requirements (password + 2FA)...")
            
            # Check if user has usable password
            has_password = user.has_usable_password()
            print(f"🔑 Has usable password: {has_password}")
            
            if not has_password:
                print("❌ User doesn't have usable password")
                errors.append("Password is required to access seller account. Please set up a password first.")
            else:
                # Additional check for passwords starting with '!' (Django's unusable password prefix)
                if hasattr(user, 'password') and user.password and user.password.startswith('!'):
                    print("❌ User has invalid password (starts with '!')")
                    errors.append("Invalid password detected. Please reset your password to continue.")
                else:
                    print("✅ User has valid password")
            
            # Check if 2FA is enabled for non-OAuth users
            two_factor_enabled = getattr(user, 'two_factor_enabled', False)
            print(f"🔐 Two-factor enabled: {two_factor_enabled}")
            
            if not two_factor_enabled:
                print("❌ User doesn't have 2FA enabled")
                errors.append("Two-factor authentication must be enabled to access seller account.")
            else:
                print("✅ User has 2FA enabled")
        else:
            print("✅ OAuth user - no additional password/2FA requirements for session")
        
        result = {
            'valid': len(errors) == 0,
            'errors': errors
        }
        
        print(f"📊 SESSION VALIDATION RESULT: {result}")
        return result
    
    @staticmethod
    def create_stripe_account(user, country='US', business_type='individual'):
        """
        Create a Stripe Express account for the seller.
        
        Args:
            user (CustomUser): The user to create account for
            country (str): Country code for the account
            business_type (str): Type of business account ('individual' or 'company')
            
        Returns:
            dict: Result with account_id and success status
        """
        print(f"🔄 STRIPE ACCOUNT CREATION START for user: {user.email}")
        print(f"📋 Request parameters: country={country}, business_type={business_type}")
        
        try:
            # First validate user requirements
            print("🔍 Validating user requirements...")
            validation = StripeConnectService.validate_seller_requirements(user)
            print(f"✅ Validation result: {validation}")
            
            if not validation['valid']:
                print(f"❌ Validation failed with errors: {validation['errors']}")
                return {
                    'success': False,
                    'errors': validation['errors']
                }
            
            print("✅ User validation passed, creating Stripe account...")
            
            # Prepare account creation parameters
            account_params = {
                'country': country,
                'email': user.email,
                'business_type': business_type,
                'capabilities': {
                    'card_payments': {'requested': True},
                    'transfers': {'requested': True},
                },
                'settings': {
                    'payouts': {
                        'schedule': {
                            'interval': 'manual',  # Marketplace controls payouts
                        }
                    }
                },
                'controller': {
                    'requirement_collection': 'application',  # Required for disable_stripe_user_authentication
                    'losses': {
                        'payments': 'application'  # Application controls loss handling
                    },
                    'fees': {
                        'payer': 'application'  # Application controls fee collection
                    },
                    'stripe_dashboard': {
                        'type': 'none'  # Must be 'none' when controlling requirements
                    }
                }
            }
            
            # Add individual info for individual accounts
            if business_type == 'individual':
                account_params['individual'] = {
                    'email': user.email,
                    'first_name': user.first_name or '',
                    'last_name': user.last_name or '',
                }
            
            print(f"📝 Account creation parameters: {account_params}")
            
            # Create Stripe Express account with controller (type is implied)
            print("🚀 Calling Stripe Account.create API...")
            account = stripe.Account.create(**account_params)
            
            print(f"✅ Stripe account created successfully!")
            print(f"🆔 Account ID: {account.id}")
            print(f"📊 Account status: charges_enabled={account.charges_enabled}, details_submitted={account.details_submitted}")
            
            # Save account ID to user model
            print(f"💾 Saving account ID to user model...")
            user.stripe_account_id = account.id
            user.save(update_fields=['stripe_account_id'])
            
            print(f"✅ Account ID saved to user {user.email}")
            logger.info(f"Created Stripe account {account.id} for user {user.email}")
            
            return {
                'success': True,
                'account_id': account.id,
                'account': account
            }
            
        except stripe.error.StripeError as e:
            print(f"❌ STRIPE API ERROR: {str(e)}")
            print(f"🔍 Error type: {type(e).__name__}")
            print(f"📄 Error details: {e.user_message if hasattr(e, 'user_message') else 'No user message'}")
            if hasattr(e, 'error') and hasattr(e.error, 'code'):
                print(f"🏷️ Error code: {e.error.code}")
            if hasattr(e, 'error') and hasattr(e.error, 'param'):
                print(f"📌 Error param: {e.error.param}")
                
            logger.error(f"Stripe error creating account for user {user.email}: {str(e)}")
            return {
                'success': False,
                'errors': [f"Failed to create Stripe account: {str(e)}"]
            }
        except Exception as e:
            print(f"❌ UNEXPECTED ERROR: {str(e)}")
            print(f"🔍 Error type: {type(e).__name__}")
            import traceback
            print(f"📋 Full traceback: {traceback.format_exc()}")
            
            logger.error(f"Unexpected error creating Stripe account for user {user.email}: {str(e)}")
            return {
                'success': False,
                'errors': [f"An unexpected error occurred: {str(e)}"]
            }
    
    @staticmethod
    def create_account_session(user):
        """
        Create an Account Session for seller onboarding using Stripe Connect JS.
        
        Args:
            user (CustomUser): The user with Stripe account
            
        Returns:
            dict: Result with account session data
        """
        print(f"🔄 STRIPE ACCOUNT SESSION CREATION START for user: {user.email}")
        print(f"🆔 User's Stripe Account ID: {user.stripe_account_id}")
        
        try:
            # Validate user requirements for session access (allows existing accounts)
            print("🔍 Validating user session requirements...")
            validation = StripeConnectService.validate_seller_session_requirements(user)
            print(f"✅ Session validation result: {validation}")
            
            if not validation['valid']:
                print(f"❌ Session validation failed with errors: {validation['errors']}")
                return {
                    'success': False,
                    'errors': validation['errors']
                }

            if not user.stripe_account_id:
                print("❌ User does not have a Stripe account ID")
                return {
                    'success': False,
                    'errors': ['User does not have a Stripe account. Please create an account first.']
                }
            
            print("✅ User has valid Stripe account, creating account session...")
            
            # Prepare account session parameters
            session_params = {
                'account': user.stripe_account_id,
                'components': {
                    "account_onboarding": {
                        "enabled": True,
                        "features": {
                            "disable_stripe_user_authentication": True,
                            "external_account_collection": True
                        }
                    }
                },
                'settings': {
                    'payouts': {
                        'schedule': {
                            'interval': 'manual'  # 🔑 disables automatic payouts
                        }
                    }
                }
            }
            
            print(f"📝 Account session parameters: {session_params}")
            
            print("🚀 Calling Stripe AccountSession.create API...")
            account_session = stripe.AccountSession.create(**session_params)
            
            print(f"✅ Account session created successfully!")
            print(f"🔑 Client secret: {account_session.client_secret[:20]}...{account_session.client_secret[-10:] if len(account_session.client_secret) > 30 else account_session.client_secret}")
            print(f"⏰ Session expires at: {account_session.expires_at}")
            
            logger.info(f"Created account session for user {user.email} with account {user.stripe_account_id}")
            
            return {
                'success': True,
                'client_secret': account_session.client_secret,
                'account_id': user.stripe_account_id
            }
            
        except stripe.error.StripeError as e:
            print(f"❌ STRIPE API ERROR in session creation: {str(e)}")
            print(f"🔍 Error type: {type(e).__name__}")
            print(f"📄 Error details: {e.user_message if hasattr(e, 'user_message') else 'No user message'}")
            if hasattr(e, 'error') and hasattr(e.error, 'code'):
                print(f"🏷️ Error code: {e.error.code}")
            if hasattr(e, 'error') and hasattr(e.error, 'param'):
                print(f"📌 Error param: {e.error.param}")
                
            logger.error(f"Stripe error creating account session for user {user.email}: {str(e)}")
            return {
                'success': False,
                'errors': [f"Failed to create account session: {str(e)}"]
            }
        except Exception as e:
            print(f"❌ UNEXPECTED ERROR in session creation: {str(e)}")
            print(f"🔍 Error type: {type(e).__name__}")
            import traceback
            print(f"📋 Full traceback: {traceback.format_exc()}")
            
            logger.error(f"Unexpected error creating account session for user {user.email}: {str(e)}")
            return {
                'success': False,
                'errors': [f"An unexpected error occurred: {str(e)}"]
            }
    
    @staticmethod
    def get_account_status(user):
        """
        Get the status of a user's Stripe account.
        
        Args:
            user (CustomUser): The user to check
            
        Returns:
            dict: Account status information
        """
        try:
            if not user.stripe_account_id:
                return {
                    'success': True,
                    'has_account': False,
                    'status': 'no_account'
                }
            
            account = stripe.Account.retrieve(user.stripe_account_id)
            
            return {
                'success': True,
                'has_account': True,
                'account_id': account.id,
                'status': 'active' if account.details_submitted and account.charges_enabled else 'incomplete',
                'details_submitted': account.details_submitted,
                'charges_enabled': account.charges_enabled,
                'payouts_enabled': account.payouts_enabled,
                'requirements': account.requirements,
                'account_data': account
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error getting account status for user {user.email}: {str(e)}")
            return {
                'success': False,
                'errors': [f"Failed to get account status: {str(e)}"]
            }
        except Exception as e:
            logger.error(f"Unexpected error getting account status for user {user.email}: {str(e)}")
            return {
                'success': False,
                'errors': [f"An unexpected error occurred: {str(e)}"]
            }
    
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
                return {
                    'success': False,
                    'errors': [f"No user found with Stripe account ID: {account_id}"]
                }
            
            # Update user's seller status if account is complete
            if account_data.get('details_submitted') and account_data.get('charges_enabled'):
                if hasattr(user, 'profile'):
                    user.profile.is_verified_seller = True
                    user.profile.save(update_fields=['is_verified_seller'])
                    logger.info(f"Updated user {user.email} to verified seller status")
            
            logger.info(f"Processed account.updated webhook for user {user.email}")
            
            return {
                'success': True,
                'user_id': user.id,
                'account_id': account_id
            }
            
        except Exception as e:
            logger.error(f"Error processing account.updated webhook: {str(e)}")
            return {
                'success': False,
                'errors': [f"Failed to process webhook: {str(e)}"]
            }


def create_seller_account(user, country='US', business_type='individual'):
    """
    Convenience function to create a Stripe account for a seller.
    
    Args:
        user (CustomUser): The user to create account for
        country (str): Country code
        business_type (str): Business type
        
    Returns:
        dict: Creation result
    """
    return StripeConnectService.create_stripe_account(user, country, business_type)


def create_seller_account_session(user):
    """
    Convenience function to create an account session for seller onboarding.
    
    Args:
        user (CustomUser): The user with Stripe account
        
    Returns:
        dict: Account session creation result
    """
    return StripeConnectService.create_account_session(user)


def validate_seller_eligibility(user):
    """
    Convenience function to validate seller eligibility.
    
    Args:
        user (CustomUser): The user to validate
        
    Returns:
        dict: Validation result
    """
    return StripeConnectService.validate_seller_requirements(user)


def create_transfer_to_connected_account(amount, currency, destination_account_id, transfer_group=None, metadata=None):
    """
    Create a transfer to a connected Stripe account.
    
    Args:
        amount (int): Amount in cents to transfer
        currency (str): Currency code (e.g., 'usd')
        destination_account_id (str): Stripe connected account ID to transfer to
        transfer_group (str, optional): Transfer group ID for grouping related transfers
        metadata (dict, optional): Additional metadata for the transfer
        
    Returns:
        dict: Transfer result with success status and transfer data
    """
    logger.info(f"Creating transfer of {amount} {currency} to account {destination_account_id}")
    
    try:
        # Validate inputs
        if not destination_account_id:
            return {
                'success': False,
                'errors': ['Destination account ID is required']
            }
            
        if amount <= 0:
            return {
                'success': False,
                'errors': ['Transfer amount must be greater than 0']
            }
        
        # Prepare transfer parameters
        transfer_params = {
            'amount': amount,
            'currency': currency.lower(),
            'destination': destination_account_id,

        }
        
        # Add optional parameters
        if transfer_group:
            transfer_params['transfer_group'] = transfer_group
            
        if metadata:
            transfer_params['metadata'] = metadata
        
        logger.info(f"Transfer parameters: {transfer_params}")
        # Create the transfer
        transfer = stripe.Transfer.create(**transfer_params)
        
        logger.info(f"Transfer created successfully: {transfer.id}")
        logger.info(f"Transfer status: {transfer.object}")
        
        

        
        return {
            'success': True,
            'transfer_id': transfer.id,
            'amount': transfer.amount,
            'currency': transfer.currency,
            'destination': transfer.destination,
            'transfer_group': transfer.transfer_group,
            'created': transfer.created,
            'transfer_data': transfer
        }
        
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error creating transfer: {str(e)}")
        return {
            'success': False,
            'errors': [f"Failed to create transfer: {str(e)}"]
        }
    except Exception as e:
        logger.error(f"Unexpected error creating transfer: {str(e)}")
        return {
            'success': False,
            'errors': [f"An unexpected error occurred: {str(e)}"]
        }