# Order Creation Flow Changes

## Overview

Updated the payment system to create orders **before** Stripe checkout rather than after payment completion. This provides better order tracking, inventory management, and user experience.

## Key Changes

### Before (Old Flow)
1. User clicks checkout → Cart exists
2. Stripe checkout session created with `cart_id` 
3. User completes payment → Webhook triggered
4. **Webhook creates order** from cart items
5. Cart cleared after order creation
6. Receipt email sent

### After (New Flow)  
1. User clicks checkout → Cart exists
2. **Order created immediately** with `pending_payment` status
3. Stock reserved and cart cleared immediately
4. Stripe checkout session created with `order_id`
5. User completes payment → Webhook triggered
6. **Webhook updates existing order** to `payment_confirmed`
7. Receipt email sent

## Benefits

✅ **Better UX**: Orders exist immediately, users can track them even during payment
✅ **Inventory Management**: Stock reserved immediately when order created
✅ **Simplified Webhooks**: Only update existing orders, no complex cart handling
✅ **Security**: Webhook verifies user owns the order before updating
✅ **Reliability**: Reduced race conditions and cart state issues

## Technical Changes

### `create_checkout_session` Function
**File**: `payment_system/views.py`

**New Behavior**:
- Creates `Order` with `pending_payment` status
- Creates `OrderItem` records from cart items
- Reserves stock immediately
- Clears cart after order creation
- Passes `order_id` in Stripe metadata (instead of `cart_id`)
- Returns `orderId` to frontend for tracking

### `handle_successful_payment` Function
**File**: `payment_system/views.py`

**New Behavior**:
- Extracts `order_id` from metadata (instead of `cart_id`)
- Finds existing order and verifies user ownership
- Updates order status from `pending_payment` → `payment_confirmed`
- Updates payment status from `pending` → `paid`
- Adds shipping address from Stripe checkout
- Locks order and creates payment tracker
- Sends receipt email

### Return URL Update
- Old: `http://localhost:5173/order-success/`
- New: `http://localhost:5173/order-success/{order.id}`

Frontend can now immediately show order details even before webhook processing.

## Order Status Flow

```
Create Checkout → pending_payment (Order Created)
                        ↓
Complete Payment → payment_confirmed (Webhook Updates)
                        ↓
Ship Order → awaiting_shipment
                        ↓
                  shipped → delivered
```

## Database Schema Impact

**No schema changes required** - using existing order status values:
- `pending_payment` (default status)
- `payment_confirmed` (set by webhook)

## Error Handling

### Checkout Session Creation
- Cart validation before order creation
- Atomic transaction for order + items creation
- Stock availability checking
- Graceful rollback on errors

### Webhook Processing
- Order existence verification
- User ownership validation
- Idempotent updates (can process same webhook multiple times)
- Graceful handling of missing metadata

## Testing

### Test Script
Run `python test_new_order_flow.py` to verify:
- Order creation with `pending_payment` status
- Cart clearing after order creation
- Webhook order status updates
- User ownership verification
- Payment tracker creation
- Email receipt sending

### Test Results
✅ Order created before payment (pending_payment status)
✅ Cart cleared immediately after order creation  
✅ Webhook only updates existing order status
✅ User ownership verification in webhook
✅ Stock reserved immediately when order created
✅ Receipt email sent after payment confirmation

## Frontend Integration

### API Response Changes
**`create_checkout_session` now returns**:
```json
{
  "clientSecret": "cs_test_...",
  "orderId": "uuid-order-id"
}
```

### Success URL
- Frontend should handle `/order-success/{orderId}` route
- Can immediately display order details using the order ID
- No need to wait for webhook processing for basic order info

## Rollback Plan

If issues arise, rollback involves:
1. Revert `payment_system/views.py` changes
2. Update frontend to handle old success URL format
3. No database changes needed (old flow will work with existing orders)

## Security Considerations

✅ **Enhanced Security**:
- Webhook verifies user owns order before updating
- Order ownership validation prevents unauthorized updates
- Stock reservation prevents overselling
- Atomic transactions ensure data consistency

## Performance Impact

✅ **Improved Performance**:
- Fewer database operations in webhook
- No cart lookups in webhook processing
- Immediate stock reservation prevents race conditions
- Simplified webhook logic reduces processing time

## Migration Notes

- **No user impact**: Changes are backend-only
- **No data migration**: Existing orders unaffected
- **Backward compatible**: Old pending orders will still work
- **Gradual rollout**: Can enable per-user or percentage basis