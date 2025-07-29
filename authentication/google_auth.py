import os
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken

# Import Google auth modules only when needed to avoid import errors
try:
    from google.auth.transport import requests
    from google.oauth2 import id_token
    GOOGLE_AUTH_AVAILABLE = True
except ImportError as e:
    GOOGLE_AUTH_AVAILABLE = False
    print(f"❌ Google auth libraries import failed: {e}")
    print("Warning: Google auth libraries not available. Install with: pip install google-auth google-auth-oauthlib")

User = get_user_model()

class GoogleAuth:
    @staticmethod
    def verify_google_token(token):
        """
        Verify Google ID token and return user information
        """
        print(f"🔍 GOOGLE_AUTH_AVAILABLE status: {GOOGLE_AUTH_AVAILABLE}")
        if not GOOGLE_AUTH_AVAILABLE:
            return None, "Google authentication libraries not installed"
        
        try:
            # Get Google OAuth client ID from environment
            client_id = os.getenv('GOOGLE_OAUTH_CLIENT_ID')
            print(f"🔍 Google OAuth Client ID from env: {'***' + client_id[-20:] if client_id else 'NOT SET'}")
            
            if not client_id:
                print("❌ Google OAuth client ID not configured in environment")
                return None, "Google OAuth client ID not configured"
            
            print(f"🔍 Verifying token with client_id...")
            # Verify the token
            idinfo = id_token.verify_oauth2_token(
                token, 
                requests.Request(), 
                client_id
            )
            print(f"✅ Token verified successfully")
            print(f"🔍 Token info - ISS: {idinfo.get('iss')}")
            print(f"🔍 Token info - AUD: {idinfo.get('aud')}")
            print(f"🔍 Token info - EMAIL: {idinfo.get('email')}")
            print(f"🔍 Token info - NAME: {idinfo.get('name')}")
            
            # Check if the token is issued by Google
            if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
                print(f"❌ Invalid token issuer: {idinfo['iss']}")
                return None, "Invalid token issuer"
            
            print("✅ Token verification complete - returning user info")
            return idinfo, None
            
        except ValueError as e:
            print(f"❌ Token validation error: {str(e)}")
            return None, f"Invalid token: {str(e)}"
        except Exception as e:
            print(f"❌ Token verification exception: {str(e)}")
            return None, f"Token verification failed: {str(e)}"
    
    @staticmethod
    def get_or_create_user(google_user_info):
        """
        Get or create user from Google user information
        """
        print(f"🔍 Getting/creating user from Google info...")
        email = google_user_info.get('email')
        print(f"🔍 User email from Google: {email}")
        
        if not email:
            print("❌ No email provided by Google")
            return None, "Email not provided by Google"
        
        # Check if user already exists
        print(f"🔍 Checking if user exists with email: {email}")
        try:
            user = User.objects.get(email=email)
            print(f"✅ Existing user found: {user.email}")
            # If user exists but signed up with regular registration,
            # we can link their Google account
            return user, None
        except User.DoesNotExist:
            print(f"🔍 User doesn't exist, creating new user...")
            # Create new user from Google info
            try:
                user = User.objects.create_user(
                    username=email,  # Use email as username
                    email=email,
                    first_name=google_user_info.get('given_name', ''),
                    last_name=google_user_info.get('family_name', ''),
                    is_email_verified=True,  # Google accounts are pre-verified
                    is_active=True,  # Google users are immediately active
                )
                print(f"✅ New user created: {user.email}")
                return user, None
            except Exception as e:
                print(f"❌ User creation failed: {str(e)}")
                return None, f"Failed to create user: {str(e)}"
    
    @staticmethod
    def generate_tokens(user):
        """
        Generate JWT tokens for the user
        """
        refresh = RefreshToken.for_user(user)
        return {
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }