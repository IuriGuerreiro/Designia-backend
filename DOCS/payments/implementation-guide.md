# Payment System Implementation Guide

## Quick Start

This guide provides technical implementation details for integrating with Designia's payment system.

## Database Schema

### Model Relationships

```
User (Django Auth)
├── StripeAccount (One-to-One)
├── Payment (Foreign Key - buyer)
├── SellerPayout (Foreign Key - seller)
└── RefundRequest (Foreign Key - requested_by)

Order (Marketplace)
├── Payment (One-to-Many)
└── RefundRequest (One-to-Many)

OrderItem (Marketplace)
└── SellerPayout (One-to-One)
```

### Key Model Fields

#### Payment Model
```python
# 30-day hold system
hold_until = models.DateTimeField()  # Auto-calculated: created_at + 30 days
is_held = models.BooleanField(default=True)
hold_released_at = models.DateTimeField(null=True, blank=True)

# Stripe integration
payment_intent_id = models.CharField(max_length=255, unique=True)
stripe_metadata = models.JSONField(default=dict, blank=True)

# Financial tracking
amount = models.DecimalField(max_digits=10, decimal_places=2)
application_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
```

#### SellerPayout Model
```python
# Automatic payout creation after hold release
payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='seller_payouts')
seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payouts_received')
stripe_account = models.ForeignKey(StripeAccount, on_delete=models.CASCADE)

# Calculated amounts
amount = models.DecimalField(max_digits=10, decimal_places=2)  # Net amount to seller
application_fee = models.DecimalField(max_digits=10, decimal_places=2)  # Fee deducted
```

## API Integration

### Frontend Payment Processing

#### 1. Create Payment Intent
```javascript
// Frontend payment processing
const processPayment = async (orderId, paymentMethodId) => {
  try {
    const response = await fetch('/api/payments/process/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({
        order_id: orderId,
        payment_method_id: paymentMethodId
      })
    });

    const result = await response.json();
    
    if (result.requires_action) {
      // Handle 3D Secure or additional authentication
      const { error } = await stripe.confirmCardPayment(
        result.payment_intent.client_secret
      );
      
      if (error) {
        console.error('Payment confirmation failed:', error);
        return { success: false, error };
      }
    }
    
    return result;
  } catch (error) {
    console.error('Payment processing error:', error);
    return { success: false, error };
  }
};
```

#### 2. Check Payment Status
```javascript
const getPaymentStatus = async (paymentId) => {
  const response = await fetch(`/api/payments/status/${paymentId}/`, {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });
  return response.json();
};
```

### Seller Onboarding

#### 1. Create Stripe Account
```javascript
const createStripeAccount = async (country = 'US') => {
  const response = await fetch('/api/payments/stripe-account/create/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify({ country })
  });
  
  const result = await response.json();
  
  if (result.onboarding_url) {
    // Redirect user to Stripe onboarding
    window.location.href = result.onboarding_url;
  }
  
  return result;
};
```

#### 2. Check Account Status
```javascript
const getAccountStatus = async () => {
  const response = await fetch('/api/payments/stripe-account/status/', {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });
  return response.json();
};
```

### Refund Management

#### 1. Request Refund
```javascript
const requestRefund = async (orderId, amount, reason, description) => {
  const response = await fetch('/api/payments/refund/request/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify({
      order_id: orderId,
      amount: amount,
      reason: reason,
      description: description
    })
  });
  return response.json();
};
```

## Backend Integration

### Custom Payment Processing

#### Extending Payment Logic
```python
# custom_payments/models.py
from payment_system.models import Payment

class CustomPayment(Payment):
    # Add custom fields
    custom_metadata = models.JSONField(default=dict)
    special_processing = models.BooleanField(default=False)
    
    def custom_hold_logic(self):
        """Override default 30-day hold if needed"""
        if self.special_processing:
            # Custom hold period for special cases
            self.hold_until = timezone.now() + timedelta(days=14)
        super().save()
```

#### Custom Payout Distribution
```python
# Override payout creation for custom fee structures
def create_custom_seller_payouts(payment):
    """Custom payout logic for different fee structures"""
    for item in payment.order.items.all():
        seller = item.product.seller
        
        # Custom fee calculation based on seller tier
        if hasattr(seller, 'seller_profile'):
            fee_rate = seller.seller_profile.commission_rate
        else:
            fee_rate = 0.05  # Default 5%
        
        seller_amount = item.total_price
        item_fee = seller_amount * fee_rate
        net_amount = seller_amount - item_fee
        
        SellerPayout.objects.create(
            payment=payment,
            seller=seller,
            stripe_account=seller.stripe_account,
            amount=net_amount,
            application_fee=item_fee,
            order_item=item
        )
```

### Webhook Handling

#### Custom Webhook Processors
```python
# custom_webhooks.py
from payment_system.views import stripe_webhook

def handle_custom_event(event_data):
    """Handle custom Stripe events"""
    if event_data['type'] == 'transfer.paid':
        # Update payout status when transfer completes
        transfer = event_data['data']['object']
        try:
            payout = SellerPayout.objects.get(
                stripe_transfer_id=transfer['id']
            )
            payout.status = 'paid'
            payout.paid_at = timezone.now()
            payout.save()
            
            # Send notification to seller
            send_payout_notification(payout.seller, payout)
            
        except SellerPayout.DoesNotExist:
            logger.error(f"Payout not found for transfer: {transfer['id']}")

# Add to webhook handler in views.py
elif event['type'] == 'transfer.paid':
    handle_custom_event(event)
```

## Hold Release Automation

### Celery Task Implementation
```python
# payment_system/tasks.py
from celery import shared_task
from django.utils import timezone
from .models import Payment

@shared_task
def release_payment_holds():
    """Automated task to release eligible payment holds"""
    eligible_payments = Payment.objects.filter(
        is_held=True,
        status='succeeded',
        hold_until__lte=timezone.now()
    )
    
    released_count = 0
    failed_count = 0
    
    for payment in eligible_payments:
        try:
            if payment.release_hold():
                released_count += 1
                logger.info(f"Released hold for payment {payment.id}")
            else:
                failed_count += 1
                logger.warning(f"Failed to release hold for payment {payment.id}")
        except Exception as e:
            failed_count += 1
            logger.error(f"Error releasing hold for payment {payment.id}: {e}")
    
    return {
        'released': released_count,
        'failed': failed_count,
        'timestamp': timezone.now().isoformat()
    }
```

### Cron Job Setup
```bash
# Add to crontab for daily hold release at 2 AM
0 2 * * * /path/to/your/project/manage.py release_holds
```

### Django Management Command
```python
# payment_system/management/commands/release_holds.py
from django.core.management.base import BaseCommand
from payment_system.models import Payment
from django.utils import timezone

class Command(BaseCommand):
    help = 'Release eligible payment holds'
    
    def handle(self, *args, **options):
        eligible_payments = Payment.objects.filter(
            is_held=True,
            status='succeeded',
            hold_until__lte=timezone.now()
        )
        
        released_count = 0
        for payment in eligible_payments:
            if payment.release_hold():
                released_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully released {released_count} payment holds'
            )
        )
```

## Testing Implementation

### Test Data Setup
```python
# tests/test_payments.py
from django.test import TestCase
from django.contrib.auth import get_user_model
from payment_system.models import Payment, StripeAccount
from marketplace.models import Order, OrderItem
from datetime import timedelta
from django.utils import timezone

class PaymentSystemTestCase(TestCase):
    def setUp(self):
        User = get_user_model()
        
        # Create test users
        self.buyer = User.objects.create_user(
            username='testbuyer',
            email='buyer@test.com'
        )
        self.seller = User.objects.create_user(
            username='testseller', 
            email='seller@test.com'
        )
        
        # Create Stripe account for seller
        self.stripe_account = StripeAccount.objects.create(
            user=self.seller,
            stripe_account_id='acct_test123',
            is_active=True,
            charges_enabled=True,
            payouts_enabled=True
        )
        
        # Create test order
        self.order = Order.objects.create(
            buyer=self.buyer,
            total_amount=100.00,
            status='pending'
        )
    
    def test_payment_hold_system(self):
        """Test 30-day hold system"""
        payment = Payment.objects.create(
            payment_intent_id='pi_test123',
            order=self.order,
            buyer=self.buyer,
            amount=100.00,
            application_fee=5.00,
            status='succeeded'
        )
        
        # Check hold is automatically set
        self.assertTrue(payment.is_held)
        self.assertIsNotNone(payment.hold_until)
        
        # Check hold period is 30 days
        expected_hold = payment.created_at + timedelta(days=30)
        self.assertEqual(payment.hold_until.date(), expected_hold.date())
    
    def test_hold_release(self):
        """Test hold release and payout creation"""
        # Create payment with past hold date
        payment = Payment.objects.create(
            payment_intent_id='pi_test123',
            order=self.order,
            buyer=self.buyer,
            amount=100.00,
            application_fee=5.00,
            status='succeeded',
            hold_until=timezone.now() - timedelta(days=1)  # Past due
        )
        
        # Release hold
        self.assertTrue(payment.release_hold())
        
        # Check hold was released
        payment.refresh_from_db()
        self.assertFalse(payment.is_held)
        self.assertIsNotNone(payment.hold_released_at)
        
        # Check seller payouts were created
        self.assertTrue(payment.seller_payouts.exists())
```

## Performance Optimization

### Database Indexing
```python
# Add to models for better query performance
class Payment(models.Model):
    # ... existing fields ...
    
    class Meta:
        db_table = 'payments'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'is_held']),
            models.Index(fields=['hold_until']),
            models.Index(fields=['payment_intent_id']),
            models.Index(fields=['created_at']),
        ]
```

### Query Optimization
```python
# Optimized queries for dashboard data
def get_seller_dashboard_data(seller_id):
    """Optimized seller dashboard queries"""
    from django.db.models import Sum, Count, Q
    
    payouts = SellerPayout.objects.filter(seller_id=seller_id)
    
    dashboard_data = payouts.aggregate(
        total_earnings=Sum('amount', filter=Q(status='paid')),
        pending_payouts=Sum('amount', filter=Q(status='pending')),
        total_orders=Count('order_item__order', distinct=True),
        pending_orders=Count('order_item__order', 
                           filter=Q(order_item__order__status='pending'),
                           distinct=True)
    )
    
    return dashboard_data
```

## Security Implementation

### Input Validation
```python
# payment_system/validators.py
from django.core.exceptions import ValidationError
from decimal import Decimal

def validate_payment_amount(amount):
    """Validate payment amounts"""
    if amount <= 0:
        raise ValidationError("Payment amount must be positive")
    
    if amount > Decimal('10000.00'):
        raise ValidationError("Payment amount exceeds maximum limit")
    
    return amount

def validate_refund_amount(refund_amount, original_amount):
    """Validate refund amounts"""
    if refund_amount <= 0:
        raise ValidationError("Refund amount must be positive")
    
    if refund_amount > original_amount:
        raise ValidationError("Refund amount cannot exceed original payment")
    
    return refund_amount
```

### Permission Classes
```python
# payment_system/permissions.py
from rest_framework.permissions import BasePermission

class IsPaymentOwnerOrAdmin(BasePermission):
    """Permission for payment access"""
    def has_object_permission(self, request, view, obj):
        return (
            obj.buyer == request.user or
            request.user.is_staff or
            request.user.is_superuser
        )

class IsSellerOrAdmin(BasePermission):
    """Permission for seller payout access"""
    def has_object_permission(self, request, view, obj):
        return (
            obj.seller == request.user or
            request.user.is_staff or
            request.user.is_superuser
        )
```

This implementation guide provides the technical foundation for integrating with the payment system across both backend Django and frontend applications (React/Expo).