# Stripe Webhook Setup Guide

## Overview
This guide explains how to set up Stripe webhooks to automatically create orders and lock carts when payments are successful.

## Webhook Implementation
The webhook endpoint is located at: `POST /api/payments/stripe_webhook/`

### Events Handled
- `checkout.session.completed` - Creates order and locks cart when payment is successful

## Environment Variables Required

Add this to your `.env` file:

```bash
# Stripe Webhook Secret (get this from Stripe Dashboard)
STRIPE_WEBHOOK_SECRET=whsec_your_webhook_secret_here
```

## How to Get the Webhook Secret

1. Go to [Stripe Dashboard](https://dashboard.stripe.com/)
2. Navigate to **Developers** → **Webhooks**
3. Click **"Add endpoint"**
4. Set the endpoint URL to: `https://yourdomain.com/api/payments/stripe_webhook/`
   - For local testing: `https://your-ngrok-url.ngrok.io/api/payments/stripe_webhook/`
5. Select events to send: `checkout.session.completed`
6. Click **"Add endpoint"**
7. Click on your new webhook
8. In the **"Signing secret"** section, click **"Reveal"**
9. Copy the secret (starts with `whsec_`) and add it to your `.env` file

## Local Testing with ngrok

For local development, you can use ngrok to expose your local server:

```bash
# Install ngrok if you haven't already
npm install -g ngrok

# Expose your local Django server
ngrok http 8000

# Use the HTTPS URL from ngrok for your webhook endpoint
# Example: https://abc123.ngrok.io/api/payments/stripe_webhook/
```

## Webhook Flow

1. **User completes payment** → Stripe checkout session is completed
2. **Stripe sends webhook** → POST request to `/api/payments/stripe_webhook/`
3. **Webhook verifies signature** → Ensures request is from Stripe
4. **Process payment success** → Lock cart and create order
5. **Order created** → User receives confirmation

## What Happens When Payment Succeeds

1. **Cart is locked** → `cart.locked = True` (prevents further modifications)
2. **Order is created** with:
   - Status: `confirmed`
   - Payment status: `paid`
   - Shipping address from Stripe form
   - All cart items converted to order items
3. **Product stock is reduced** for each ordered item
4. **User gets new active cart** for future purchases

## Testing Webhook

You can test the webhook by making a successful payment through the checkout form. Check the Django server logs for webhook processing messages:

```
✅ Payment successful for session: cs_test_...
🔒 Cart 123 locked
📦 Order abc-123 created
✅ Order abc-123 created successfully with 2 items
```

## Webhook Security

The webhook endpoint:
- ✅ Verifies Stripe signature using webhook secret
- ✅ Uses CSRF exemption (required for external webhooks)  
- ✅ Uses database transactions for atomicity
- ✅ Handles duplicate webhook calls gracefully
- ✅ Logs all processing steps for debugging

## Troubleshooting

### Common Issues

1. **"Webhook secret not configured"**
   - Make sure `STRIPE_WEBHOOK_SECRET` is set in your `.env` file

2. **"Invalid signature"**
   - Check that the webhook secret matches the one in Stripe Dashboard
   - Ensure the endpoint URL is correct

3. **"User or cart not found"**
   - Verify that user_id and cart_id are being passed in Stripe metadata
   - Check that the cart exists and belongs to the user

4. **"Cart already locked"**
   - This is normal - it means the webhook was called multiple times
   - The system handles this gracefully and skips duplicate processing

### Debug Mode

To see detailed webhook processing, check your Django server logs. All important steps are logged with emojis for easy identification:

- ✅ Success messages
- ❌ Error messages  
- ℹ️ Info messages
- 🔒 Cart locking
- 📦 Order creation
- ⚠️ Warnings

## Production Deployment

When deploying to production:

1. Update the webhook URL in Stripe Dashboard to your production domain
2. Make sure `STRIPE_WEBHOOK_SECRET` is set in your production environment
3. Ensure your server can receive POST requests on the webhook endpoint
4. Monitor webhook delivery in the Stripe Dashboard