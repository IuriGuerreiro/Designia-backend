# Payment Tracking System - Setup Guide

## Overview

Complete payment tracking system that creates detailed payment records when `checkout.session.completed` webhook is received from Stripe. Each seller gets their own payment transaction with manual payment release controls.

## Database Tables Created

### PaymentTransaction
- **Purpose**: Tracks individual payments per seller
- **Key Fields**: seller, buyer, gross_amount, platform_fee, stripe_fee, net_amount, status
- **Status Flow**: `pending` → `held` → `released` (manual release only)

### PaymentHold  
- **Purpose**: Manages payment holding periods
- **Key Fields**: reason, hold_days, planned_release_date, status
- **Manual Release**: Admin must manually release payments after verification

### PaymentItem
- **Purpose**: Detailed item tracking within each payment
- **Key Fields**: product, quantity, unit_price, total_price

## Webhook Integration

When `checkout.session.completed` is received:

1. **PaymentTransaction** created for each seller in the order
2. **PaymentHold** created with **fixed 7-day hold period** for all purchases
3. **PaymentItems** created for detailed tracking
4. Platform fees (5%) and Stripe fees (2.9% + $0.30) calculated
5. Status set to `held` until **manual release**
6. **Planned release date** automatically calculated (current date + 7 days)

## Fee Structure

```python
platform_fee = gross_amount * 0.05        # 5% platform fee
stripe_fee = gross_amount * 0.029 + 0.30  # 2.9% + $0.30 Stripe fee
net_amount = gross_amount - platform_fee - stripe_fee
```

## Manual Payment Release

### Admin Interface
All payment releases are done manually through the Django admin interface:

1. Navigate to **Payment System** → **Payment Transactions**
2. Filter by `status = held` to see payments requiring release
3. Select payments to release
4. Use "Manually release selected held payments" action
5. Payments will be marked as `released` with admin audit trail

## Admin Interface

### PaymentTransaction Admin
- View all payment transactions by seller
- See hold status and days remaining
- Bulk release actions for held payments
- Filter by status, seller, date
- Inline view of payment items

### PaymentHold Admin  
- Manage payment holds
- Manual release capabilities
- View hold reasons and dates
- Track who created/released holds

### PaymentItem Admin
- Detailed view of items in each payment
- Product information and pricing
- Link to original order items

## Usage Examples

### Check Payments Ready to Release
```python
from payment_system.models import PaymentHold
from django.utils import timezone

ready_holds = PaymentHold.objects.filter(
    status='active',
    planned_release_date__lte=timezone.now()
)
```

### Manual Payment Release
```python
# Release a specific hold (admin only)
hold = PaymentHold.objects.get(id=hold_id)
success = hold.release_hold(
    released_by=request.user,
    notes="Manually released by admin after verification"
)
```

### Get Seller's Pending Payments
```python
from payment_system.models import PaymentTransaction

pending_payments = PaymentTransaction.objects.filter(
    seller=seller,
    status='held'
).select_related('payment_hold')
```

## Monitoring

### Key Metrics to Monitor
- Number of held payments
- Average hold duration
- Platform fee revenue
- Failed releases

### Database Queries
```sql
-- Payments ready to release
SELECT COUNT(*) FROM payment_holds 
WHERE status = 'active' AND planned_release_date <= NOW();

-- Revenue by seller (held)
SELECT seller_id, SUM(net_amount) as pending_revenue
FROM payment_transactions 
WHERE status = 'held' 
GROUP BY seller_id;

-- Platform fees collected today
SELECT SUM(platform_fee) as daily_platform_fees
FROM payment_transactions 
WHERE DATE(payment_received_date) = CURDATE();
```

## Security Considerations

1. **Payment holds prevent fraud**: Manual verification before release
2. **Audit trail**: Complete tracking of who released payments when  
3. **Admin controls**: Only admin staff can release payments
4. **Manual oversight**: Human verification for all payment releases

## Troubleshooting

### Common Issues

1. **Missing payment transactions**
   - Verify webhook is receiving `checkout.session.completed`
   - Check for errors in webhook processing
   - Ensure order has multiple sellers (creates multiple transactions)

2. **Incorrect fee calculations**
   - Verify platform fee rate (default 5%)
   - Check Stripe fee calculation (2.9% + $0.30)
   - Ensure decimal precision is maintained

3. **Payment release issues**
   - Verify admin has proper permissions
   - Check payment status is 'held' before release
   - Ensure hold exists for the payment

### Logs to Check
- Django logs for webhook processing errors
- Admin action logs for payment releases
- Stripe webhook delivery logs

## Next Steps

1. **Test webhook** with actual Stripe payments
2. **Train admin staff** on payment release procedures
3. **Setup monitoring** for held payments requiring attention
4. **Configure alerts** for payments held longer than expected
5. **Establish verification procedures** before releasing payments

## Files Modified/Created

- `payment_system/models.py` - Added PaymentTransaction, PaymentHold, PaymentItem models
- `payment_system/admin.py` - Added comprehensive admin interfaces with manual release actions
- `payment_system/views.py` - Updated webhook to create payment tracking records
- Migration: `payment_system/migrations/0002_*` - Database schema
- `PAYMENT_TRACKING_SETUP.md` - This setup documentation