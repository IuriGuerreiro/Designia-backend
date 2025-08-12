# Payment System Workflow Documentation

## Overview

Designia's payment system implements a comprehensive marketplace payment solution using Stripe Connect with a 30-day payment hold system to accommodate returns and ensure buyer protection.

## System Architecture

### Core Components

1. **Payment Processing**: Handles order payments with Stripe PaymentIntents
2. **30-Day Hold System**: Automatically holds payments for return policy protection
3. **Seller Payouts**: Automated seller compensation after hold release
4. **Refund Management**: Complete refund request and approval workflow
5. **Webhook Integration**: Real-time payment status updates from Stripe

### Database Models

#### StripeAccount
- Represents Stripe Connect accounts for marketplace sellers
- Links Django users to their Stripe Express accounts
- Tracks onboarding and verification status

#### Payment
- Main payment record for marketplace transactions
- Implements 30-day automatic hold system
- Connects orders to Stripe PaymentIntents

#### SellerPayout
- Individual payouts to sellers after payment hold release
- Tracks Stripe Transfer IDs for each seller payment
- Handles marketplace fee distribution

#### RefundRequest
- Manages buyer refund requests with approval workflow
- Links to original payments for processing
- Tracks refund status through Stripe

## Payment Flow Workflow

### 1. Order Creation and Payment

```
Buyer places order → Order created → Payment processing initiated
```

**Process:**
1. Buyer selects items and proceeds to checkout
2. Order is created in pending status
3. Payment processing view is called with order ID and payment method
4. System calculates total amount and marketplace fees
5. Stripe PaymentIntent is created with application fees
6. Payment record is created with 30-day hold automatically set

**Key Features:**
- Automatic 30-day hold period calculation
- Marketplace fee calculation (configurable percentage)
- Payment Intent metadata includes order and buyer information

### 2. Payment Hold System (30 Days)

```
Payment succeeded → 30-day hold starts → Automatic release → Seller payouts
```

**Hold Logic:**
- All successful payments are automatically held for 30 days
- Hold period starts from payment creation timestamp
- `hold_until` field is automatically set to `created_at + 30 days`
- `is_held` flag tracks current hold status

**Automatic Release:**
- Daily automated job checks for eligible holds
- Payments are released when `timezone.now() >= hold_until`
- Release triggers automatic seller payout creation
- Hold release timestamp is recorded for auditing

### 3. Seller Payout Distribution

```
Hold released → Calculate seller shares → Create payout records → Process Stripe transfers
```

**Payout Calculation:**
1. System iterates through all order items
2. For each item, identifies the seller
3. Calculates seller's share: `item_price - (item_price * fee_percentage)`
4. Creates SellerPayout record for each seller
5. Automatically processes Stripe Transfer to seller's connected account

**Multi-Seller Support:**
- Single order can have items from multiple sellers
- Each seller gets individual payout based on their items
- Marketplace fees are proportionally distributed
- Independent payout processing for each seller

### 4. Refund Request Workflow

```
Buyer requests refund → Admin review → Approval/Rejection → Stripe refund processing
```

**Request Process:**
1. Buyer creates refund request with reason and description
2. Request is created in 'pending' status
3. Admin reviews request details and order information
4. Admin approves or rejects with optional notes

**Refund Processing:**
1. Approved requests trigger Stripe refund creation
2. Refund amount is deducted from original PaymentIntent
3. If payment was already released, seller payouts may be adjusted
4. Refund status is tracked through completion

## API Endpoints

### Payment Processing

**POST /api/payments/process/**
- Processes order payments
- Creates PaymentIntent and Payment record
- Returns payment status and next steps

**GET /api/payments/status/{payment_id}/**
- Retrieves current payment status
- Shows hold information and days remaining
- Available to payment owner and admin

### Stripe Account Management

**POST /api/payments/stripe-account/create/**
- Creates Stripe Connect account for sellers
- Returns onboarding URL for account setup
- Links account to user profile

**GET /api/payments/stripe-account/status/**
- Retrieves current account verification status
- Updates local status from Stripe
- Shows onboarding completion state

### Seller Payouts

**GET /api/payments/seller-payouts/**
- Lists payout history for authenticated seller
- Shows pending, processing, and completed payouts
- Includes order and item details

### Refund Management

**POST /api/payments/refund/request/**
- Creates new refund request
- Validates refund amount against original payment
- Sets status to pending for admin review

### Administrative Functions

**POST /api/payments/release-holds/**
- Admin endpoint to manually release eligible holds
- Processes batch hold releases
- Returns count of released payments

## Security Features

### Authentication & Authorization
- All endpoints require user authentication
- Payment access restricted to order participants
- Admin-only endpoints for hold management
- Seller-specific payout data access

### Data Protection
- Payment data encrypted in database
- Stripe tokens stored securely
- Webhook signature verification
- Input validation on all endpoints

### Financial Security
- Payment amounts validated against orders
- Refund amounts cannot exceed original payment
- Application fees calculated server-side
- Webhook events logged for audit trail

## Hold Release Automation

### Automated Processing
The system includes automated hold release functionality:

```python
def release_eligible_holds():
    """Daily job to release eligible payment holds"""
    eligible_payments = Payment.objects.filter(
        is_held=True,
        status='succeeded',
        hold_until__lte=timezone.now()
    )
    
    for payment in eligible_payments:
        payment.release_hold()  # Creates seller payouts automatically
```

### Manual Release
Administrators can manually release holds through the API:
- Useful for customer service situations
- Maintains audit trail of manual releases
- Triggers same payout creation process

## Error Handling

### Payment Failures
- Failed payments are marked with appropriate status
- Detailed error logging for debugging
- User-friendly error messages returned
- Automatic retry logic for webhook processing

### Payout Failures
- Failed payouts are marked with failure reason
- Sellers are notified of payout issues
- Manual retry capability for administrators
- Detailed failure logging for resolution

## Monitoring & Logging

### Webhook Events
- All Stripe webhooks are logged in WebhookEvent model
- Failed webhook processing is tracked
- Automatic retry attempts for failed webhooks
- Event data stored for debugging

### Payment Tracking
- Complete audit trail for all payment activities
- Transaction logs for financial reconciliation
- Status change history for payments and payouts
- Detailed error logging for troubleshooting

## Integration Points

### Frontend Integration
The payment system provides RESTful APIs for frontend consumption:
- React components can integrate with payment endpoints
- Expo mobile app uses same API structure
- Real-time status updates through webhook processing

### Stripe Integration
- Uses Stripe Connect for marketplace functionality
- PaymentIntents for secure payment processing
- Express accounts for seller onboarding
- Webhooks for real-time status updates

## Configuration

### Environment Variables Required
```
STRIPE_SECRET_KEY=sk_...
STRIPE_PUBLISHABLE_KEY=pk_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_APPLICATION_FEE_PERCENT=5.0
FRONTEND_URL=https://yourdomain.com
```

### Django Settings
```python
# Add to INSTALLED_APPS
INSTALLED_APPS = [
    ...
    'payment_system',
    ...
]

# Add to URL patterns
urlpatterns = [
    ...
    path('api/payments/', include('payment_system.urls')),
    ...
]
```

## Testing Considerations

### Test Data
- Use Stripe test mode for development
- Test with various payment methods
- Validate hold release automation
- Test multi-seller order scenarios

### Test Cases
1. **Successful Payment Flow**: Complete order-to-payout cycle
2. **Payment Failures**: Handle various Stripe error scenarios
3. **Hold Release**: Test both automated and manual releases
4. **Refund Processing**: Full refund workflow testing
5. **Multi-Seller Orders**: Complex payout distribution
6. **Webhook Processing**: Simulate Stripe webhook events

## Deployment Notes

### Production Setup
1. Configure production Stripe keys
2. Set up webhook endpoints in Stripe Dashboard
3. Configure automated hold release job (cron/celery)
4. Set up monitoring for payment failures
5. Configure logging for financial audit trail

### Maintenance Tasks
- Regular webhook event cleanup
- Payment reconciliation reports
- Hold release monitoring
- Seller payout verification
- Failed transaction review

This payment system provides a robust foundation for marketplace transactions with built-in buyer protection through the 30-day hold system while ensuring sellers receive timely payments after the return period.