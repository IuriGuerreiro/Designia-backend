# Authentication Events System

Event-driven architecture for authentication module using Django signals.

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Available Events](#available-events)
3. [Listening to Events](#listening-to-events)
4. [Dispatching Events](#dispatching-events)
5. [Event Data](#event-data)
6. [Use Cases](#use-cases)
7. [Best Practices](#best-practices)

---

## Overview

The authentication module uses **domain events** to enable loose coupling and extensibility. When important business actions occur (user registers, seller approved, etc.), events are dispatched that other parts of the system can react to.

### Architecture

```
Service Layer (dispatch) → Domain Events → Signal Handlers (react)
```

**Example Flow:**
1. `AuthService.register()` creates a new user
2. Service dispatches `user_registered` event
3. Signal handler sends welcome email
4. Analytics handler tracks conversion
5. All handlers run independently

### Benefits

✅ **Loose Coupling** - Services don't know about side effects
✅ **Extensibility** - Add new handlers without changing services
✅ **Testability** - Mock or disable handlers in tests
✅ **Observability** - Centralized logging of business events
✅ **Scalability** - Can publish to event bus for microservices

---

## Available Events

### Authentication Events

#### `user_registered`

**Dispatched when:** User completes registration

**Signal Parameters:**
- `sender` - CustomUser class
- `user` - CustomUser instance
- `email_sent` (bool) - Whether verification email was sent
- `ip_address` (str) - Registration IP address (optional)

**Example Handler:**
```python
from django.dispatch import receiver
from authentication.domain.events import user_registered

@receiver(user_registered)
def handle_user_registered(sender, user, email_sent, ip_address=None, **kwargs):
    # Send welcome email
    # Track analytics
    # Initialize user preferences
    pass
```

---

#### `user_email_verified`

**Dispatched when:** User verifies their email address

**Signal Parameters:**
- `sender` - CustomUser class
- `user` - CustomUser instance
- `ip_address` (str) - Verification IP (optional)

**Use Cases:**
- Send welcome email (now that email is verified)
- Grant access to restricted features
- Track conversion funnel

---

#### `user_login_successful`

**Dispatched when:** User successfully completes login

**Signal Parameters:**
- `sender` - CustomUser class
- `user` - CustomUser instance
- `ip_address` (str) - Login IP (optional)
- `required_2fa` (bool) - Whether 2FA was required

**Use Cases:**
- Track login analytics
- Check for suspicious login patterns
- Send security alert for new device
- Update last login timestamp

---

#### `user_login_failed`

**Dispatched when:** Login attempt fails

**Signal Parameters:**
- `sender` - None
- `email` (str) - Email used for login attempt
- `reason` (str) - Failure reason (wrong_password, user_not_found, etc.)
- `ip_address` (str) - Login attempt IP (optional)

**Use Cases:**
- Track failed login attempts
- Rate limiting
- Alert on brute force attempts
- Track analytics for login issues

---

#### `user_2fa_enabled` / `user_2fa_disabled`

**Dispatched when:** User enables/disables 2FA

**Signal Parameters:**
- `sender` - CustomUser class
- `user` - CustomUser instance

---

### Seller Application Events

#### `seller_application_submitted`

**Dispatched when:** Seller application is submitted or resubmitted

**Signal Parameters:**
- `sender` - SellerApplication class
- `application` - SellerApplication instance
- `is_resubmission` (bool) - True if resubmission after rejection

**Use Cases:**
- Send confirmation email to applicant
- Notify admins of new application
- Track application analytics
- Trigger review workflow

**Example:**
```python
@receiver(seller_application_submitted)
def handle_seller_application_submitted(sender, application, is_resubmission, **kwargs):
    if is_resubmission:
        logger.info(f"Resubmission from {application.user.email}")
    else:
        # Notify admins of new application
        notify_admins_new_application(application)
```

---

#### `seller_application_approved`

**Dispatched when:** Admin approves seller application

**Signal Parameters:**
- `sender` - SellerApplication class
- `application` - SellerApplication instance
- `admin_user` - CustomUser instance (admin who approved)
- `new_seller` - CustomUser instance (newly approved seller)

**Use Cases:**
- Send approval email to new seller
- Send seller onboarding guide
- Grant seller permissions
- Track conversion analytics
- Notify other admins

**Example:**
```python
@receiver(seller_application_approved)
def handle_seller_application_approved(sender, application, admin_user, new_seller, **kwargs):
    # Send approval email with onboarding guide
    send_seller_approval_email(new_seller, application)

    # Track analytics
    track_event('seller_approved', new_seller.id, {
        'seller_type': application.seller_type,
        'approved_by': admin_user.id
    })
```

---

#### `seller_application_rejected`

**Dispatched when:** Admin rejects seller application

**Signal Parameters:**
- `sender` - SellerApplication class
- `application` - SellerApplication instance
- `admin_user` - CustomUser instance (admin who rejected)
- `reason` (str) - Rejection reason

**Use Cases:**
- Send rejection email with reason
- Track rejection analytics
- Schedule follow-up communication

---

### Profile Events

#### `profile_updated`

**Dispatched when:** User updates their profile

**Signal Parameters:**
- `sender` - CustomUser class
- `user` - CustomUser instance
- `updated_fields` (list) - List of field names updated
- `profile_completion` (int) - Profile completion percentage

**Use Cases:**
- Track which fields are commonly updated
- Send profile completion milestone emails
- Update search index for user profiles
- Trigger recommendations based on profile data

**Example:**
```python
@receiver(profile_updated)
def handle_profile_updated(sender, user, updated_fields, profile_completion, **kwargs):
    # Send milestone email
    if profile_completion == 100 and not user.profile.milestone_100_sent:
        send_profile_complete_email(user)
        user.profile.milestone_100_sent = True
        user.profile.save()
```

---

#### `profile_picture_uploaded`

**Dispatched when:** User uploads a new profile picture

**Signal Parameters:**
- `sender` - CustomUser class
- `user` - CustomUser instance
- `file_key` (str) - S3 key of uploaded file

**Use Cases:**
- Generate thumbnails
- Update CDN cache
- Notify connections of profile update
- Track analytics

---

#### `profile_picture_deleted`

**Dispatched when:** User deletes their profile picture

**Signal Parameters:**
- `sender` - CustomUser class
- `user` - CustomUser instance

**Use Cases:**
- Clean up CDN cache
- Delete related thumbnails
- Track analytics

---

## Listening to Events

### Method 1: Using @receiver Decorator

```python
# authentication/signals.py or myapp/handlers.py

from django.dispatch import receiver
from authentication.domain.events import user_registered

@receiver(user_registered)
def my_handler(sender, user, email_sent, **kwargs):
    # React to user registration
    logger.info(f"User registered: {user.email}")

    # Send analytics event
    analytics.track('user_registered', user.id)

    # Send to CRM
    crm.create_contact(user)
```

**Important:** Handlers are automatically registered when the module is imported. Make sure to import in your app's `apps.py`:

```python
# myapp/apps.py
class MyAppConfig(AppConfig):
    name = 'myapp'

    def ready(self):
        import myapp.handlers  # Import to register handlers
```

---

### Method 2: Manual Connection

```python
from authentication.domain.events import user_registered

def my_handler(sender, user, **kwargs):
    # Handle event
    pass

# Connect manually
user_registered.connect(my_handler)
```

---

### Method 3: Conditional Handlers

```python
@receiver(user_registered)
def handle_user_registered(sender, user, email_sent, **kwargs):
    # Only run for specific conditions
    if user.language == 'es':
        send_spanish_welcome_email(user)
```

---

## Dispatching Events

Events are dispatched automatically by services using `EventDispatcher`.

### From Service Layer

```python
from authentication.domain.events import EventDispatcher

# In AuthService.register()
EventDispatcher.dispatch_user_registered(
    user=new_user,
    email_sent=True,
    ip_address=get_client_ip(request)
)
```

### Custom Events

To add a new event:

1. **Define signal in `domain/events.py`:**
```python
user_password_changed = Signal()  # Add new signal
```

2. **Add EventDispatcher method:**
```python
class EventDispatcher:
    @staticmethod
    def dispatch_user_password_changed(user):
        logger.info(f"[EVENT] Password changed: {user.email}")
        user_password_changed.send(sender=user.__class__, user=user)
```

3. **Create handler in `signals.py`:**
```python
@receiver(user_password_changed)
def handle_user_password_changed(sender, user, **kwargs):
    # Send security alert email
    send_password_changed_email(user)
```

4. **Dispatch from service:**
```python
# In AuthService.change_password()
EventDispatcher.dispatch_user_password_changed(user)
```

---

## Event Data

Events carry structured data. Use dataclasses for complex events:

```python
# domain/events.py
@dataclass
class UserRegisteredEvent:
    user: CustomUser
    email_sent: bool
    registration_ip: Optional[str] = None
```

Access in handlers:

```python
@receiver(user_registered)
def handle(sender, user, email_sent, ip_address=None, **kwargs):
    event = UserRegisteredEvent(
        user=user,
        email_sent=email_sent,
        registration_ip=ip_address
    )
    # Use structured event object
```

---

## Use Cases

### 1. Analytics Tracking

```python
@receiver(user_registered)
def track_registration(sender, user, email_sent, **kwargs):
    analytics.track('user_registered', user.id, {
        'email_sent': email_sent,
        'signup_method': 'email',
        'language': user.language,
    })
```

### 2. Email Automation

```python
@receiver(seller_application_approved)
def send_seller_onboarding(sender, new_seller, **kwargs):
    # Send onboarding email series
    email_campaign.enroll(new_seller, 'seller_onboarding')
```

### 3. External System Integration

```python
@receiver(user_email_verified)
def sync_to_crm(sender, user, **kwargs):
    # Sync to external CRM
    crm_api.create_contact({
        'email': user.email,
        'name': f"{user.first_name} {user.last_name}",
        'verified': True,
    })
```

### 4. Security Monitoring

```python
@receiver(user_login_failed)
def monitor_failed_logins(sender, email, reason, ip_address=None, **kwargs):
    # Track failed attempts
    failed_count = FailedLoginAttempt.count_recent(email)

    if failed_count > 5:
        # Alert security team
        security_alerts.send_alert(
            'Brute force detected',
            f"Email: {email}, IP: {ip_address}"
        )
```

### 5. Gamification / Achievements

```python
@receiver(profile_updated)
def award_profile_badges(sender, user, profile_completion, **kwargs):
    if profile_completion >= 50 and not user.has_badge('profile_50'):
        user.award_badge('profile_50')
        send_badge_earned_email(user, 'Profile Halfway There!')
```

---

## Best Practices

### 1. Keep Handlers Lightweight

Handlers should be fast. For heavy operations, queue background tasks:

```python
@receiver(user_registered)
def handle_user_registered(sender, user, **kwargs):
    # ✅ GOOD - Queue background task
    send_welcome_email_task.delay(user.id)

    # ❌ BAD - Slow synchronous operation
    # generate_pdf_report(user)  # This blocks!
```

### 2. Handle Errors Gracefully

Don't let handler failures break the main flow:

```python
@receiver(user_registered)
def handle_user_registered(sender, user, **kwargs):
    try:
        external_api.create_contact(user)
    except Exception as e:
        logger.error(f"Failed to sync to CRM: {e}")
        # Don't re-raise - allow other handlers to run
```

### 3. Use **kwargs for Forward Compatibility

Always accept `**kwargs` to handle future parameters:

```python
@receiver(user_registered)
def my_handler(sender, user, email_sent, **kwargs):
    # ✅ GOOD - Accepts future parameters
    pass

def bad_handler(sender, user, email_sent):
    # ❌ BAD - Breaks if new parameter added
    pass
```

### 4. Test with Mocked Signals

In unit tests, disable or mock signal handlers:

```python
from django.test.utils import override_settings

@override_settings(SIGNALS_ENABLED=False)
def test_registration():
    # Test without triggering signal handlers
    pass
```

Or mock specific handlers:

```python
@patch('authentication.signals.handle_user_registered')
def test_registration(mock_handler):
    # Test with mocked handler
    auth_service.register(...)
    assert mock_handler.called
```

### 5. Document Handler Dependencies

If handlers have external dependencies, document them:

```python
@receiver(user_registered)
def sync_to_mailchimp(sender, user, **kwargs):
    """
    Sync new user to Mailchimp mailing list.

    Requirements:
    - MAILCHIMP_API_KEY must be set
    - MAILCHIMP_LIST_ID must be configured
    """
    pass
```

### 6. Order Matters (Sometimes)

Handlers run in order of connection. If order matters, use `dispatch_uid`:

```python
@receiver(user_registered, dispatch_uid='first_handler')
def first_handler(sender, **kwargs):
    pass

@receiver(user_registered, dispatch_uid='second_handler')
def second_handler(sender, **kwargs):
    pass
```

---

## Troubleshooting

### Handlers Not Running?

1. **Check registration:** Ensure signals are imported in `apps.py`:
```python
class AuthenticationConfig(AppConfig):
    def ready(self):
        import authentication.signals  # Must import!
```

2. **Check sender:** Make sure signal sender matches:
```python
# Dispatched with sender=CustomUser
user_registered.send(sender=CustomUser, ...)

# Handler receives sender=CustomUser
@receiver(user_registered)
def handle(sender, **kwargs):
    assert sender == CustomUser
```

3. **Check exceptions:** Handler exceptions are silently caught. Add logging:
```python
@receiver(user_registered)
def handle(sender, **kwargs):
    try:
        # Your code
    except Exception as e:
        logger.exception("Handler failed")
        raise
```

---

## Future: Event Bus Integration

Currently using Django signals (synchronous, in-process).

**Future plans:**
- Publish to Redis pub/sub for distributed systems
- Use RabbitMQ or Kafka for microservices
- Event sourcing for audit trail
- CQRS patterns for read models

**Migration path:**
```python
# Current (Django signals)
EventDispatcher.dispatch_user_registered(user, ...)

# Future (Event bus)
event_bus.publish(UserRegisteredEvent(user, ...))
```

Services won't change - only the dispatcher implementation!

---

**Questions?** Check the [main README](./README.md) or [Services documentation](./SERVICES.md).
