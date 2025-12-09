# Authentication Module - Refactored Architecture

**Version:** Phase 1 SOLID Refactoring
**Status:** ✅ Service Layer Complete
**Last Updated:** 2025-12-09

---

## 🎯 Overview

The authentication module has been refactored following **SOLID principles** and **Clean Architecture** patterns. Business logic has been extracted from thick controllers into testable service classes with dependency injection.

### Key Improvements

✅ **Service Layer** - All business logic in isolated, testable services
✅ **Infrastructure Abstraction** - Email and storage providers abstracted behind interfaces
✅ **Thin Controllers** - Views are simple HTTP adapters (coming in Phase 3)
✅ **Domain Events** - Observable authentication events for loose coupling
✅ **Testability** - 100% mockable dependencies for unit testing

---

## 📂 Architecture

```
authentication/
├── domain/                          # Business Logic Layer
│   ├── services/
│   │   ├── auth_service.py         # Login, register, email verify, 2FA
│   │   ├── seller_service.py       # Seller applications workflow
│   │   ├── profile_service.py      # Profile management
│   │   └── results.py              # Result objects for services
│   └── events.py                   # Domain events & signals
│
├── infra/                          # Infrastructure Layer
│   ├── mail/
│   │   ├── email_interface.py      # Abstract email provider
│   │   ├── django_email_provider.py# Production email implementation
│   │   └── mock_email_provider.py  # Test mock
│   └── storage/
│       ├── storage_interface.py    # Abstract storage provider
│       ├── s3_storage_provider.py  # S3/MinIO implementation
│       └── local_storage_provider.py# Test/dev mock
│
├── api/                            # HTTP/API Layer (Phase 3)
│   └── views/                      # Thin controllers (TODO)
│
├── models.py                       # Domain models
├── serializers.py                  # API serializers
├── signals.py                      # Signal handlers for events
└── apps.py                         # App config + signal registration
```

---

## 🚀 Quick Start

### Using Services in Views

```python
from authentication.domain.services import AuthService
from authentication.infra.mail import DjangoEmailProvider

# Initialize service with dependencies
email_provider = DjangoEmailProvider()
auth_service = AuthService(email_provider)

# Use service in view
def my_view(request):
    result = auth_service.login(
        email=request.data.get('email'),
        password=request.data.get('password'),
        request=request
    )

    if result.success:
        return Response({
            'user': UserSerializer(result.user).data,
            'access_token': result.access_token,
            'refresh_token': result.refresh_token,
        })
    else:
        return Response({'error': result.error}, status=400)
```

### Using Events

```python
from authentication.domain.events import EventDispatcher

# Dispatch events from services
EventDispatcher.dispatch_user_registered(
    user=new_user,
    email_sent=True,
    ip_address=get_client_ip(request)
)
```

### Listening to Events

Signal handlers in `signals.py` automatically respond to events:

```python
from django.dispatch import receiver
from authentication.domain.events import user_registered

@receiver(user_registered)
def handle_user_registered(sender, user, email_sent, **kwargs):
    # Send welcome email, track analytics, etc.
    pass
```

---

## 📖 Service Documentation

### AuthService

**Purpose:** Core authentication business logic

**Methods:**
- `login(email, password, request)` - Authenticate user, handle 2FA
- `register(email, username, password, ...)` - Create new user + send verification
- `verify_email(token)` - Verify email with token
- `send_verification_email(user, request)` - Send/resend verification email
- `handle_2fa_login(user_id, code)` - Complete 2FA challenge
- `send_2fa_code(user, purpose, request)` - Send 2FA code

**Returns:** `LoginResult`, `RegisterResult`, or `Result` objects

[Full documentation](./SERVICES.md#authservice)

### SellerService

**Purpose:** Seller application workflow

**Methods:**
- `submit_application(user, application_data, workshop_photos)` - Submit/resubmit
- `approve_application(application_id, admin_user)` - Approve and upgrade to seller
- `reject_application(application_id, admin_user, reason)` - Reject with reason
- `get_application_status(user)` - Query application status

**Returns:** `Result` objects with success/error

[Full documentation](./SERVICES.md#sellerservice)

### ProfileService

**Purpose:** Profile management

**Methods:**
- `update_profile(user, profile_data)` - Update with permission checks
- `upload_profile_picture(user, image_file)` - Upload to S3
- `delete_profile_picture(user)` - Delete from S3
- `get_profile_picture_url(user, expires_in)` - Get presigned URL

**Returns:** `Result` objects with success/error

[Full documentation](./SERVICES.md#profileservice)

---

## 🧪 Testing

### Unit Tests (Fast, Isolated)

```python
from authentication.domain.services import AuthService
from authentication.infra.mail import MockEmailProvider

def test_login_with_valid_credentials():
    # Mock email provider
    mock_email = MockEmailProvider()
    auth_service = AuthService(email_provider=mock_email)

    # Test login
    result = auth_service.login('user@example.com', 'password123')

    assert result.success
    assert result.user.email == 'user@example.com'
```

### Integration Tests (Real DB, Real API)

```python
from rest_framework.test import APITestCase

class TestLoginAPI(APITestCase):
    def test_login_endpoint_returns_jwt_tokens(self):
        # Create test user
        user = CustomUser.objects.create_user(...)

        # Call API
        response = self.client.post('/api/auth/login/', {
            'email': user.email,
            'password': 'password123'
        })

        assert response.status_code == 200
        assert 'access' in response.data
```

---

## 🔌 Events System

Authentication events enable loose coupling and extensibility.

### Available Events

**Authentication:**
- `user_registered` - User completes registration
- `user_email_verified` - Email verification complete
- `user_login_successful` - Successful login
- `user_login_failed` - Failed login attempt
- `user_2fa_enabled` / `user_2fa_disabled`

**Seller Applications:**
- `seller_application_submitted` - New/resubmitted application
- `seller_application_approved` - Admin approves
- `seller_application_rejected` - Admin rejects

**Profile:**
- `profile_updated` - Profile fields changed
- `profile_picture_uploaded` / `profile_picture_deleted`

[Full event documentation](./EVENTS.md)

---

## 🔄 Migration Guide

### For Developers

**Phase 3 (In Progress):** Views are being refactored to use services.

**Current state:**
- ✅ Services implemented
- ✅ Infrastructure abstracted
- ✅ Events system in place
- ⏳ Views not yet refactored (still using old utils)

**Next steps:**
1. Views will be refactored to thin HTTP adapters
2. Old `utils.py` functions will be deprecated
3. Tests will be added for all services

### For Other Apps

If your app imports from `authentication`:

**❌ Don't import:**
```python
from authentication.utils import send_verification_email  # OLD
from authentication.models import EmailRequestAttempt     # OLD
```

**✅ Do import:**
```python
from authentication.interface import (                    # NEW (Phase 4)
    can_send_email,
    record_email_sent,
    get_client_ip_address
)
```

---

## 📊 Code Quality

**Service Layer:**
- **AuthService:** ~450 lines, single responsibility
- **SellerService:** ~300 lines, single responsibility
- **ProfileService:** ~250 lines, single responsibility

**Infrastructure:**
- All dependencies injected (no hardcoded infrastructure)
- Fully mockable for testing
- Clean separation of concerns

**Events:**
- Observable domain events
- Loose coupling between modules
- Extensible for future features

---

## 🛠️ Development

### Adding a New Service Method

1. Add method to service class
2. Dispatch relevant domain events
3. Write unit tests with mocked dependencies
4. Write integration tests with real API

### Adding a New Event

1. Define signal in `domain/events.py`
2. Add EventDispatcher helper method
3. Create signal handler in `signals.py`
4. Dispatch from service layer

### Running Tests

```bash
# Unit tests (fast)
pytest authentication/tests/unit/ -v

# Integration tests
pytest authentication/tests/integration/ -v

# With coverage
pytest authentication/tests/ --cov=authentication --cov-report=html
```

---

## 📝 TODO

**Phase 3:** View Layer Refactoring (In Progress)
- Refactor auth views to use AuthService
- Refactor seller views to use SellerService
- Refactor profile views to use ProfileService

**Phase 4:** Interface Contracts
- Create public interface for other apps
- Migrate payment_system to use interface

**Phase 5:** Testing & Documentation
- Achieve 80%+ test coverage
- Document API contracts
- Write migration guide

---

## 🤝 Contributing

When making changes:
1. Follow SOLID principles
2. Keep services under 500 lines
3. Inject all dependencies
4. Dispatch relevant events
5. Write tests for new features
6. Update documentation

---

## 📚 Additional Resources

- [Service Documentation](./SERVICES.md) - Detailed service API docs
- [Event Documentation](./EVENTS.md) - Event system guide
- [Testing Guide](./TESTING.md) - How to test services
- [Migration Guide](./MIGRATION_GUIDE.md) - Upgrading from old architecture

---

**Questions?** Contact the backend team or check the tech spec document.
