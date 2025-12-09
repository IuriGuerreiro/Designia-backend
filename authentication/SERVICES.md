# Service Layer Documentation

Complete API documentation for authentication services.

---

## Table of Contents

1. [AuthService](#authservice)
2. [SellerService](#sellerservice)
3. [ProfileService](#profileservice)
4. [Result Objects](#result-objects)
5. [Error Handling](#error-handling)
6. [Best Practices](#best-practices)

---

## AuthService

**Location:** `authentication/domain/services/auth_service.py`

**Purpose:** Core authentication business logic including login, registration, email verification, and 2FA.

### Constructor

```python
AuthService(email_provider: EmailProvider)
```

**Parameters:**
- `email_provider` - Email provider implementation (DjangoEmailProvider or MockEmailProvider)

**Example:**
```python
from authentication.domain.services import AuthService
from authentication.infra.mail import DjangoEmailProvider

email_provider = DjangoEmailProvider()
auth_service = AuthService(email_provider)
```

---

### Methods

#### `login(email: str, password: str, request=None) -> LoginResult`

Authenticate user with email/password, handling email verification and 2FA.

**Business Logic:**
1. Validates email and password provided
2. Checks if user exists
3. Verifies password
4. Checks email verification status
5. If 2FA enabled:
   - Checks for unused codes (avoids rate limit)
   - Sends new code if needed
   - Returns 2FA challenge
6. If no 2FA, generates JWT tokens

**Parameters:**
- `email` (str) - User's email address
- `password` (str) - User's password
- `request` (optional) - Django request for IP tracking

**Returns:** `LoginResult` with:
- `success` (bool) - True if authentication successful
- `user` - CustomUser instance (if successful)
- `access_token` (str) - JWT access token (if no 2FA)
- `refresh_token` (str) - JWT refresh token (if no 2FA)
- `requires_2fa` (bool) - True if 2FA challenge initiated
- `code_already_sent` (bool) - True if unused code exists
- `user_id` (str) - User ID for 2FA verification
- `error` (str) - Error message (if failed)

**Example:**
```python
result = auth_service.login(
    email='user@example.com',
    password='SecurePass123!',
    request=request
)

if result.success and not result.requires_2fa:
    # Login successful, no 2FA
    return {
        'user': result.user,
        'access': result.access_token,
        'refresh': result.refresh_token,
    }
elif result.requires_2fa:
    # 2FA challenge initiated
    return {
        'requires_2fa': True,
        'user_id': result.user_id,
        'message': result.message,
    }
else:
    # Login failed
    return {'error': result.error}
```

**Error Cases:**
- Missing email or password
- User not found
- Incorrect password
- Email not verified
- 2FA code send failed
- Token generation failed

---

#### `handle_2fa_login(user_id: str, code: str) -> LoginResult`

Complete login after 2FA code verification.

**Parameters:**
- `user_id` (str) - User UUID from initial login response
- `code` (str) - 6-digit 2FA code

**Returns:** `LoginResult` with tokens if verification successful

**Example:**
```python
result = auth_service.handle_2fa_login(
    user_id='123e4567-e89b-12d3-a456-426614174000',
    code='123456'
)

if result.success:
    return {
        'access': result.access_token,
        'refresh': result.refresh_token,
    }
```

---

#### `register(...) -> RegisterResult`

Register new user and send verification email.

**Full Signature:**
```python
register(
    email: str,
    username: str,
    password: str,
    first_name: str = "",
    last_name: str = "",
    request=None
) -> RegisterResult
```

**Business Logic:**
1. Creates user (inactive until email verified)
2. Sends verification email (with rate limiting)
3. Handles email send failures gracefully

**Parameters:**
- `email` (str) - User's email
- `username` (str) - Unique username
- `password` (str) - Password (will be hashed)
- `first_name` (str) - Optional first name
- `last_name` (str) - Optional last name
- `request` (optional) - Django request for IP tracking

**Returns:** `RegisterResult` with:
- `success` (bool) - True if user created
- `user` - CustomUser instance (if created)
- `email_sent` (bool) - True if verification email sent
- `error` (str) - Error message (if failed)
- `message` (str) - Success/info message

**Example:**
```python
result = auth_service.register(
    email='newuser@example.com',
    username='newuser',
    password='SecurePass123!',
    first_name='John',
    last_name='Doe',
    request=request
)

if result.success:
    if result.email_sent:
        return {'message': 'Check your email to verify account'}
    else:
        return {'message': 'Account created but email failed. Contact support.'}
```

**Note:** User is created even if email sending fails. Email can be resent later.

---

#### `verify_email(token: str) -> Result`

Verify user email with verification token.

**Parameters:**
- `token` (str) - Email verification token (UUID)

**Returns:** `Result` with success status

**Example:**
```python
result = auth_service.verify_email(token='abc-123-def-456')

if result.success:
    # User activated
    return {'message': 'Email verified successfully!'}
```

---

#### `send_verification_email(user, request=None) -> Result`

Send or resend email verification.

**Parameters:**
- `user` - CustomUser instance
- `request` (optional) - Django request for IP tracking

**Returns:** `Result` with send status

**Example:**
```python
result = auth_service.send_verification_email(
    user=request.user,
    request=request
)

if not result.success:
    # Rate limited
    return {'error': result.message}
```

---

#### `send_2fa_code(user, purpose: str, request=None) -> Result`

Send 2FA code to user email.

**Parameters:**
- `user` - CustomUser instance
- `purpose` (str) - Purpose: `login`, `enable_2fa`, `disable_2fa`, `reset_password`, etc.
- `request` (optional) - Django request

**Returns:** `Result` with code in `data['code']` (for testing)

**Example:**
```python
result = auth_service.send_2fa_code(
    user=request.user,
    purpose='enable_2fa',
    request=request
)

if result.success:
    # Code sent
    code = result.data.get('code')  # For testing only!
```

---

## SellerService

**Location:** `authentication/domain/services/seller_service.py`

**Purpose:** Seller application workflow including submission, approval, and rejection.

### Constructor

```python
SellerService(storage_provider: StorageProvider)
```

**Parameters:**
- `storage_provider` - Storage provider for workshop images (S3StorageProvider or LocalStorageProvider)

**Example:**
```python
from authentication.domain.services import SellerService
from authentication.infra.storage import S3StorageProvider

storage_provider = S3StorageProvider()
seller_service = SellerService(storage_provider)
```

---

### Methods

#### `submit_application(...) -> Result`

Submit new seller application or resubmit rejected one.

**Full Signature:**
```python
submit_application(
    user,
    application_data: Dict[str, Any],
    workshop_photos: List[UploadedFile]
) -> Result
```

**Business Logic:**
1. Checks for existing in-progress applications
2. Validates user isn't already a seller
3. Enforces 2FA requirement
4. Creates or updates application
5. Uploads workshop images
6. Transaction management (rollback on failure)

**Parameters:**
- `user` - CustomUser instance
- `application_data` (dict) with:
  - `business_name` (str)
  - `seller_type` (str) - `manufacturer`, `designer`, `restorer`, `retailer`, `artisan`
  - `motivation` (str)
  - `portfolio_url` (str)
  - `social_media_url` (str) - optional
- `workshop_photos` (list) - List of Django UploadedFile objects

**Returns:** `Result` with:
- `success` (bool)
- `message` (str)
- `data['application_id']` (int) - Application ID
- `data['images_uploaded']` (int) - Number of images uploaded

**Example:**
```python
result = seller_service.submit_application(
    user=request.user,
    application_data={
        'business_name': 'Acme Furniture',
        'seller_type': 'manufacturer',
        'motivation': 'I make beautiful chairs...',
        'portfolio_url': 'https://acme.com',
        'social_media_url': 'https://instagram.com/acme',
    },
    workshop_photos=request.FILES.getlist('workshopPhotos')
)

if result.success:
    return {'application_id': result.data['application_id']}
else:
    return {'error': result.message}
```

**Error Cases:**
- In-progress application exists
- User already a seller
- 2FA not enabled
- Image upload failed

---

#### `approve_application(application_id: int, admin_user) -> Result`

Approve seller application and upgrade user to seller role.

**Business Logic:**
1. Updates application status to "approved"
2. Upgrades user role to "seller"
3. Marks profile as verified seller
4. Records approving admin
5. Dispatches `seller_application_approved` event

**Parameters:**
- `application_id` (int) - SellerApplication ID
- `admin_user` - Admin CustomUser performing approval

**Returns:** `Result` with approval status

**Example:**
```python
result = seller_service.approve_application(
    application_id=123,
    admin_user=request.user
)

if result.success:
    return {
        'message': f"Approved {result.data['user_email']}",
        'user_id': result.data['user_id'],
    }
```

---

#### `reject_application(application_id: int, admin_user, reason: str) -> Result`

Reject seller application with reason.

**Parameters:**
- `application_id` (int) - SellerApplication ID
- `admin_user` - Admin CustomUser performing rejection
- `reason` (str) - Rejection reason

**Returns:** `Result` with rejection status

**Example:**
```python
result = seller_service.reject_application(
    application_id=123,
    admin_user=request.user,
    reason='Portfolio does not meet quality standards.'
)
```

---

#### `get_application_status(user) -> Dict[str, Any]`

Get user's most recent seller application status.

**Parameters:**
- `user` - CustomUser instance

**Returns:** Dict with:
- `has_application` (bool)
- `is_seller` (bool)
- `status` (str) - `pending`, `approved`, `rejected`, etc.
- `application_id` (int)
- `submitted_at` (datetime)
- `admin_notes` (str)
- `rejection_reason` (str)

**Example:**
```python
status = seller_service.get_application_status(request.user)

if status['has_application']:
    return {'status': status['status'], 'submitted_at': status['submitted_at']}
```

---

## ProfileService

**Location:** `authentication/domain/services/profile_service.py`

**Purpose:** Profile management including updates and profile picture operations.

### Constructor

```python
ProfileService(storage_provider: StorageProvider)
```

---

### Methods

#### `update_profile(user, profile_data: Dict[str, Any]) -> Result`

Update user profile with permission checks.

**Business Logic:**
1. Checks permissions for restricted fields
2. Restricted fields only for verified sellers/admins:
   - `phone_number`, `country_code`, `website`, `location`
   - `job_title`, `company`, `account_type`
   - Social media URLs
3. Updates profile fields
4. Recalculates completion percentage

**Parameters:**
- `user` - CustomUser instance
- `profile_data` (dict) - Fields to update

**Returns:** `Result` with:
- `data['updated_fields']` (list) - Fields updated
- `data['profile_completion']` (int) - Completion %

**Example:**
```python
result = profile_service.update_profile(
    user=request.user,
    profile_data={
        'bio': 'Furniture enthusiast',
        'location': 'New York',
        'phone_number': '+1234567890',  # Restricted field
    }
)

if not result.success:
    # Permission denied for restricted fields
    return {'error': result.message, 'restricted': result.data['restricted_fields']}
```

---

#### `upload_profile_picture(user, image_file) -> Result`

Upload profile picture to S3.

**Business Logic:**
1. Validates file size (10MB max)
2. Validates file type (jpg, png, webp)
3. Deletes old picture if exists
4. Uploads to S3
5. Updates profile.profile_picture_url
6. Generates temporary URL

**Parameters:**
- `user` - CustomUser instance
- `image_file` - Django UploadedFile

**Returns:** `Result` with:
- `data['profile_picture_url']` (str) - S3 key
- `data['profile_picture_temp_url']` (str) - Presigned URL
- `data['size']` (int) - File size in bytes
- `data['content_type']` (str) - MIME type

**Example:**
```python
result = profile_service.upload_profile_picture(
    user=request.user,
    image_file=request.FILES['profile_picture']
)

if result.success:
    return {
        'url': result.data['profile_picture_temp_url'],
        'size': result.data['size'],
    }
```

---

#### `delete_profile_picture(user) -> Result`

Delete profile picture from S3.

**Example:**
```python
result = profile_service.delete_profile_picture(request.user)
```

---

#### `get_profile_picture_url(user, expires_in: int = 3600) -> Optional[str]`

Get temporary signed URL for profile picture.

**Parameters:**
- `user` - CustomUser instance
- `expires_in` (int) - URL expiration in seconds (default: 3600 = 1 hour)

**Returns:** Presigned URL string or None

---

## Result Objects

Located in `authentication/domain/services/results.py`

### LoginResult

```python
@dataclass
class LoginResult:
    success: bool
    user: Optional[CustomUser] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    requires_2fa: bool = False
    code_already_sent: bool = False
    error: Optional[str] = None
    user_id: Optional[str] = None
    message: Optional[str] = None
```

### RegisterResult

```python
@dataclass
class RegisterResult:
    success: bool
    user: Optional[CustomUser] = None
    email_sent: bool = False
    error: Optional[str] = None
    errors: Optional[Dict[str, str]] = None
    message: Optional[str] = None
```

### Result

```python
@dataclass
class Result:
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = field(default_factory=dict)
    error: Optional[str] = None
```

---

## Error Handling

Services return Result objects with structured errors:

```python
result = service.some_method(...)

if result.success:
    # Handle success
    data = result.data
else:
    # Handle error
    error_message = result.error or result.message
    log_error(error_message)
```

**Never raise exceptions from services.** Always return Result objects.

---

## Best Practices

### 1. Dependency Injection

Always inject dependencies in constructors:

```python
# ✅ GOOD
email_provider = DjangoEmailProvider()
auth_service = AuthService(email_provider)

# ❌ BAD
auth_service = AuthService()  # Hardcoded dependencies
```

### 2. Testing with Mocks

Use mock providers for unit tests:

```python
def test_login():
    mock_email = MockEmailProvider()
    auth_service = AuthService(mock_email)

    result = auth_service.login('user@test.com', 'pass')

    assert result.success
    assert len(mock_email.twofa_codes_sent) == 0
```

### 3. Check Results

Always check `result.success`:

```python
result = auth_service.login(...)

if result.success:
    # Handle success path
else:
    # Handle error path with result.error
```

### 4. Dispatch Events

Services automatically dispatch events. Listen to them:

```python
@receiver(user_registered)
def my_handler(sender, user, **kwargs):
    # React to user registration
    pass
```

### 5. Keep Services Focused

Each service has a single responsibility:
- **AuthService** - Authentication only
- **SellerService** - Seller applications only
- **ProfileService** - Profile management only

Don't mix concerns across services.

---

**Questions?** Check the main [README](./README.md) or [Events documentation](./EVENTS.md).
