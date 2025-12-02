# Infrastructure Abstraction Layer

**Phase 1 - Week 1-2: Setup & Infrastructure Abstractions**

This package provides abstraction layers for external dependencies, implementing the **Dependency Inversion Principle** from SOLID.

## Architecture

```
infrastructure/
├── storage/           # File storage abstraction (S3, local)
├── email/            # Email service abstraction (SMTP, mock)
├── payments/         # Payment provider abstraction (Stripe)
├── notifications/    # Notification service (future)
├── container.py      # Dependency injection container
└── tests/           # Unit tests (80%+ coverage)
```

## Quick Start

### 1. Configure Settings

Add to your `settings.py`:

```python
# Storage Configuration (S3/MinIO only)
AWS_ACCESS_KEY_ID = env('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = env('AWS_SECRET_ACCESS_KEY')
AWS_STORAGE_BUCKET_NAME = env('AWS_STORAGE_BUCKET_NAME')
AWS_S3_REGION_NAME = env('AWS_S3_REGION_NAME', default='us-east-1')
AWS_S3_CUSTOM_DOMAIN = env('AWS_S3_CUSTOM_DOMAIN', default=None)
# For MinIO: Set AWS_S3_ENDPOINT_URL to your MinIO server URL

# Email Configuration
EMAIL_SERVICE_BACKEND = 'smtp'  # or 'mock' for testing
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = env('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = env('EMAIL_PORT', default=587)
EMAIL_USE_TLS = env('EMAIL_USE_TLS', default=True)
EMAIL_HOST_USER = env('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL')

# Payment Configuration
PAYMENT_PROVIDER = 'stripe'
STRIPE_SECRET_KEY = env('STRIPE_SECRET_KEY')
STRIPE_PUBLISHABLE_KEY = env('STRIPE_PUBLISHABLE_KEY')
STRIPE_WEBHOOK_SECRET = env('STRIPE_WEBHOOK_SECRET')
```

### 2. Usage in Services

```python
from infrastructure.container import container

class ProductService:
    """Example service using infrastructure abstractions."""

    def __init__(self):
        # Inject dependencies through constructor
        self.storage = container.storage()
        self.email = container.email()

    def upload_product_image(self, image_file, product_id):
        """Upload product image using storage abstraction."""
        result = self.storage.upload(
            file=image_file,
            path=f"products/{product_id}/image.jpg",
            content_type="image/jpeg",
        )
        return result.url

    def send_confirmation_email(self, user_email, product_name):
        """Send email using email abstraction."""
        from infrastructure.email import EmailMessage

        message = EmailMessage(
            subject=f"Product Created: {product_name}",
            body=f"Your product {product_name} has been created.",
            to=[user_email],
        )

        return self.email.send(message)
```

### 3. Usage in Views (Django REST Framework)

```python
from rest_framework.views import APIView
from infrastructure.container import container

class ProductImageUploadView(APIView):
    """Example view using infrastructure services."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.storage = container.storage()

    def post(self, request):
        image_file = request.FILES['image']

        # Upload using storage abstraction
        result = self.storage.upload(
            file=image_file,
            path=f"products/{request.user.id}/{image_file.name}",
            content_type=image_file.content_type,
        )

        return Response({
            'url': result.url,
            'key': result.key,
            'size': result.size,
        })
```

## Features

### Storage Abstraction

**Supported Backends**: AWS S3 / MinIO (via django-storages)

**Interface Methods**:
- `upload(file, path, content_type)` - Upload a file
- `delete(key)` - Delete a file
- `get_url(key)` - Get file URL
- `exists(key)` - Check if file exists
- `get_size(key)` - Get file size

**Usage**:
```python
from infrastructure.storage import StorageFactory

# Create S3/MinIO storage
storage = StorageFactory.create()

# Explicit creation
storage = StorageFactory.create_s3()
```

### Email Abstraction

**Supported Backends**: SMTP (Django email), Mock (testing)

**Interface Methods**:
- `send(message)` - Send single email
- `send_bulk(messages)` - Send multiple emails
- `send_html(subject, html_content, to)` - Send HTML email

**Usage**:
```python
from infrastructure.email import EmailFactory, EmailMessage

# Auto-detect from settings
email_service = EmailFactory.create()

# Send email
message = EmailMessage(
    subject="Welcome",
    body="Welcome to our platform",
    to=["user@example.com"],
    html_body="<h1>Welcome</h1>",
)

email_service.send(message)
```

### Payment Abstraction

**Supported Backends**: Stripe

**Interface Methods**:
- `create_checkout_session(amount, currency, success_url, cancel_url)` - Create payment session
- `retrieve_session(session_id)` - Get session details
- `verify_webhook(payload, signature)` - Verify webhook event
- `create_refund(payment_intent_id, amount)` - Process refund
- `retrieve_payment_intent(intent_id)` - Get payment details

**Usage**:
```python
from decimal import Decimal
from infrastructure.payments import PaymentFactory

payment_provider = PaymentFactory.create()

# Create checkout session
session = payment_provider.create_checkout_session(
    amount=Decimal("99.99"),
    currency="usd",
    success_url="https://example.com/success",
    cancel_url="https://example.com/cancel",
    metadata={"order_id": "123"},
)

print(session.url)  # Redirect user here
```

### Dependency Injection Container

**Global Container**:
```python
from infrastructure.container import container

# Get services
storage = container.storage()
email = container.email()
payment = container.payment()

# Reset cache (useful for testing)
container.reset()

# Configure for testing
container.configure_for_testing()
```

**Convenience Functions**:
```python
from infrastructure.container import get_storage, get_email, get_payment

storage = get_storage()
email = get_email()
payment = get_payment()
```

## Testing

### Running Tests

```bash
# Run all infrastructure tests
python manage.py test infrastructure.tests

# Run specific test module
python manage.py test infrastructure.tests.test_storage
python manage.py test infrastructure.tests.test_email
python manage.py test infrastructure.tests.test_payments
python manage.py test infrastructure.tests.test_container

# Run with coverage
coverage run --source='infrastructure' manage.py test infrastructure.tests
coverage report
```

### Test Configuration

For testing, configure mock services:

```python
# In your test settings or setUp()
from django.test import override_settings

@override_settings(
    EMAIL_SERVICE_BACKEND='mock',
    # S3 storage will use test credentials from settings
)
class MyTestCase(TestCase):
    def setUp(self):
        from infrastructure.container import container
        container.configure_for_testing()
```

### Mock Email Service

The mock email service stores sent messages for verification:

```python
from infrastructure.email import MockEmailService

email_service = MockEmailService()
email_service.send(message)

# Verify in tests
assert email_service.get_sent_count() == 1
last_message = email_service.get_last_message()
assert last_message.subject == "Expected Subject"
```

## Environment Variables

Create a `.env` file with:

```env
# Storage (S3)
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_STORAGE_BUCKET_NAME=your_bucket_name
AWS_S3_REGION_NAME=us-east-1

# Email (SMTP)
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your_email@gmail.com
EMAIL_HOST_PASSWORD=your_app_password
DEFAULT_FROM_EMAIL=noreply@yourapp.com

# Payment (Stripe)
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
```

## Benefits

### 1. **Testability**
- Easy to mock services in tests
- Controlled test environment with mock email service
- Fast test execution

### 2. **Flexibility**
- Switch between S3 and MinIO with configuration only
- Easy to add new email/payment providers
- Configuration-driven behavior

### 3. **Maintainability**
- Business logic decoupled from infrastructure
- Clear separation of concerns
- Easier to upgrade or replace services

### 4. **SOLID Principles**
- **S**ingle Responsibility: Each adapter handles one provider
- **O**pen/Closed: Extend with new providers without modifying existing code
- **L**iskov Substitution: All implementations are interchangeable
- **I**nterface Segregation: Focused interfaces for each service type
- **D**ependency Inversion: Depend on abstractions, not concretions

## Next Steps

After Week 1-2, proceed to:
- **Week 3-4**: Service Layer Foundation (marketplace services)
- See `DOCS/PHASE1_SOLID_REFACTORING.md` for full roadmap

## Coverage Report

Target: 80%+ test coverage

Run coverage:
```bash
coverage run --source='infrastructure' manage.py test infrastructure.tests
coverage html
# Open htmlcov/index.html
```

## Troubleshooting

### Import Errors
```python
# Ensure infrastructure is in your Python path
import sys
sys.path.append('/path/to/project')
```

### S3 Upload Fails
- Check AWS credentials in `.env`
- Verify bucket exists and has correct permissions
- Check IAM user has `s3:PutObject`, `s3:GetObject`, `s3:DeleteObject` permissions

### Email Sending Fails
- Verify SMTP credentials
- Check firewall/network allows outbound SMTP
- Enable "Less secure app access" for Gmail (or use App Password)

### Stripe Webhooks Not Working
- Verify `STRIPE_WEBHOOK_SECRET` matches Stripe dashboard
- Check webhook endpoint is publicly accessible
- Use Stripe CLI for local testing: `stripe listen --forward-to localhost:8000/api/webhooks/stripe/`
