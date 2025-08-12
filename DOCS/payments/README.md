# Payment System Documentation

This directory contains comprehensive documentation for Designia's marketplace payment system with 30-day hold functionality.

## Documentation Structure

### 📋 [Payment Workflow](payment-workflow.md)
**Complete system overview and business logic**
- 30-day payment hold system explanation
- Order-to-payout complete flow
- Refund request and approval process
- Multi-seller payout distribution
- Security features and monitoring

### 🔧 [Implementation Guide](implementation-guide.md)
**Technical integration and code examples**
- Database schema and model relationships
- Frontend API integration (React/Expo)
- Backend customization examples
- Testing implementation
- Performance optimization
- Security implementation

### 🚀 [Stripe Setup Guide](../stripe-setup.md)
**Environment configuration and Stripe integration**
- Stripe account setup and configuration
- Webhook endpoint configuration
- Environment variables and security
- Testing and production deployment

## Quick Start Guide

### 1. Setup Requirements
```bash
# Install required packages
pip install stripe django-rest-framework

# Add to Django settings
INSTALLED_APPS = [
    ...
    'payment_system',
    'rest_framework',
    ...
]
```

### 2. Environment Configuration
```env
# Stripe configuration
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_APPLICATION_FEE_PERCENT=5.0

# Application URLs
FRONTEND_URL=http://localhost:3000
```

### 3. Database Migration
```bash
python manage.py makemigrations payment_system
python manage.py migrate
```

### 4. URL Configuration
```python
# urls.py
urlpatterns = [
    path('api/payments/', include('payment_system.urls')),
]
```

## Key Features

### 🔐 30-Day Payment Hold System
- **Automatic Hold**: All payments held for 30 days automatically
- **Return Policy**: Protects buyers with comprehensive return window
- **Automated Release**: Daily job releases eligible holds
- **Manual Override**: Admin can release holds early if needed

### 💳 Stripe Connect Integration
- **Express Accounts**: Simplified seller onboarding
- **Split Payments**: Automatic marketplace fee distribution
- **Real-time Updates**: Webhook integration for status changes
- **Multi-currency**: Support for international sellers

### 🔄 Complete Payment Flow
1. **Order Creation** → Payment processing with hold
2. **30-Day Hold** → Automatic buyer protection period
3. **Hold Release** → Automated payout to sellers
4. **Multi-seller Support** → Individual payouts per seller

### 📋 Refund Management
- **Request System**: Buyers can request refunds with reasons
- **Admin Approval**: Administrative review and approval workflow
- **Stripe Processing**: Automated refund processing through Stripe
- **Hold Integration**: Works seamlessly with payment hold system

## API Endpoints Overview

### Payment Processing
- `POST /api/payments/process/` - Process order payment
- `GET /api/payments/status/{id}/` - Get payment status and hold info

### Seller Management
- `POST /api/payments/stripe-account/create/` - Create seller account
- `GET /api/payments/stripe-account/status/` - Get account verification status
- `GET /api/payments/seller-payouts/` - Get seller payout history

### Refund System
- `POST /api/payments/refund/request/` - Create refund request

### Administration
- `POST /api/payments/release-holds/` - Release eligible holds (admin only)

## Database Models

### Core Models
- **Payment**: Main payment records with 30-day hold logic
- **SellerPayout**: Individual seller payments after hold release
- **StripeAccount**: Seller Stripe Connect account information
- **RefundRequest**: Refund requests with approval workflow
- **WebhookEvent**: Stripe webhook event logging

### Model Relationships
```
User ←→ StripeAccount (One-to-One)
User ←→ Payment (Foreign Key - buyer)
User ←→ SellerPayout (Foreign Key - seller)
Order ←→ Payment (One-to-Many)
Payment ←→ SellerPayout (One-to-Many)
```

## Security Features

### Financial Security
- Payment validation against orders
- Server-side fee calculations
- Secure Stripe token handling
- Webhook signature verification

### Access Control
- User authentication required
- Payment owner/admin access only
- Seller-specific payout data
- Admin-only hold management

### Data Protection
- Encrypted sensitive data
- Audit trail logging
- Error handling and logging
- Input validation and sanitization

## Automation Features

### Hold Release Automation
```python
# Daily automated job
@shared_task
def release_payment_holds():
    # Releases all eligible holds automatically
    # Creates seller payouts
    # Sends notifications
```

### Webhook Processing
- Real-time payment status updates
- Automatic seller account status sync
- Transfer completion notifications
- Failed event retry logic

## Integration Examples

### Frontend React Integration
```javascript
// Process payment
const result = await processPayment(orderId, paymentMethodId);

// Check payment status
const status = await getPaymentStatus(paymentId);

// Create seller account
const account = await createStripeAccount('US');
```

### Django Backend Integration
```python
# Custom payment logic
payment = Payment.objects.create(
    order=order,
    buyer=user,
    amount=total,
    # 30-day hold automatically set
)

# Release hold manually
payment.release_hold()  # Creates seller payouts
```

## Monitoring & Maintenance

### Daily Tasks
- Hold release monitoring
- Failed payout review
- Webhook event cleanup
- Financial reconciliation

### Logging
- Payment processing events
- Hold release activities
- Payout distributions
- Error and failure tracking

## Support & Troubleshooting

### Common Issues
1. **Payment Failures**: Check Stripe dashboard and logs
2. **Hold Not Released**: Verify hold_until date and status
3. **Payout Failures**: Check seller account status
4. **Webhook Issues**: Verify endpoint and signature

### Debug Information
- Payment model includes detailed logging
- Webhook events stored for analysis
- Failed operations tracked with reasons
- Complete audit trail maintained

## Development Workflow

### Testing
1. Use Stripe test mode keys
2. Test payment flow with test cards
3. Verify hold release automation
4. Test refund processing
5. Validate webhook handling

### Production Deployment
1. Configure production Stripe keys
2. Set up webhook endpoints
3. Configure hold release automation
4. Set up monitoring and alerting
5. Configure logging and backup

---

For detailed technical implementation, see the [Implementation Guide](implementation-guide.md).

For business logic and workflow details, see the [Payment Workflow](payment-workflow.md).

For Stripe configuration, see the [Stripe Setup Guide](../stripe-setup.md).