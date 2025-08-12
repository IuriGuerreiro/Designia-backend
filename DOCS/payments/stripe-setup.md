# Stripe Setup Guide for Designia Marketplace

## Overview
This guide covers the complete setup process for integrating Stripe payments into the Designia marketplace with support for 30-day payment holds and multi-vendor payouts.

## Prerequisites
- Python 3.9+
- Django project setup
- Stripe account (Test and Live)
- SSL certificate for production

## 1. Stripe Account Setup

### Create Stripe Account
1. Go to [stripe.com](https://stripe.com) and create an account
2. Complete business verification for live payments
3. Enable **Express accounts** for marketplace sellers
4. Configure webhook endpoints

### Get API Keys
1. Navigate to **Developers** > **API keys**
2. Copy your **Publishable key** and **Secret key**
3. For testing, use test keys (starting with `pk_test_` and `sk_test_`)
4. For production, use live keys (starting with `pk_live_` and `sk_live_`)

### Configure Webhooks
1. Go to **Developers** > **Webhooks**
2. Add endpoint: `https://yourdomain.com/api/webhooks/stripe/`
3. Select these events:
   ```
   account.updated
   payment_intent.succeeded
   payment_intent.payment_failed
   transfer.created
   transfer.updated
   payout.created
   payout.updated
   ```

## 2. Environment Configuration

### Install Dependencies
```bash
cd Designia-backend
pip install stripe python-decouple
```

### Environment Variables
Add to your `.env` file:
```env
# Stripe Configuration
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# For production, use live keys
STRIPE_LIVE_PUBLISHABLE_KEY=pk_live_...
STRIPE_LIVE_SECRET_KEY=sk_live_...
STRIPE_LIVE_WEBHOOK_SECRET=whsec_...

# Payment Settings
PAYMENT_HOLD_DAYS=30
STRIPE_APPLICATION_FEE_PERCENT=2.9  # Your marketplace fee
```

### Django Settings
Update `settings.py`:
```python
from decouple import config
import stripe

# Stripe Configuration
STRIPE_PUBLISHABLE_KEY = config('STRIPE_PUBLISHABLE_KEY')
STRIPE_SECRET_KEY = config('STRIPE_SECRET_KEY')
STRIPE_WEBHOOK_SECRET = config('STRIPE_WEBHOOK_SECRET')

# Initialize Stripe
stripe.api_key = STRIPE_SECRET_KEY

# Payment Configuration
PAYMENT_HOLD_DAYS = config('PAYMENT_HOLD_DAYS', default=30, cast=int)
STRIPE_APPLICATION_FEE_PERCENT = config('STRIPE_APPLICATION_FEE_PERCENT', default=2.9, cast=float)

# Add to INSTALLED_APPS
INSTALLED_APPS = [
    # ... your other apps
    'payments',
]
```

## 3. Database Configuration

### Run Migrations
```bash
python manage.py makemigrations payments
python manage.py migrate
```

### Create Superuser (if not exists)
```bash
python manage.py createsuperuser
```

## 4. Stripe Connect Setup for Sellers

### Enable Express Accounts
1. In Stripe Dashboard: **Connect** > **Settings**
2. Enable **Express accounts**
3. Configure account requirements:
   - Business type: Individual or Company
   - Required information: Basic info, Bank account
   - Optional: Identity verification

### Onboarding URL Configuration
1. Set redirect URLs in Stripe Dashboard
2. Success URL: `https://yourdomain.com/seller/onboarding/success/`
3. Failure URL: `https://yourdomain.com/seller/onboarding/failure/`

## 5. Testing Setup

### Test Cards
Use these test cards for different scenarios:
```
# Successful payment
4242 4242 4242 4242

# Declined payment
4000 0000 0000 0002

# Requires authentication (3D Secure)
4000 0025 0000 3155

# Insufficient funds
4000 0000 0000 9995
```

### Test Webhooks Locally
1. Install Stripe CLI:
   ```bash
   # macOS
   brew install stripe/stripe-cli/stripe
   
   # Windows
   # Download from: https://github.com/stripe/stripe-cli/releases
   ```

2. Login and forward events:
   ```bash
   stripe login
   stripe listen --forward-to localhost:8000/api/webhooks/stripe/
   ```

## 6. Production Setup

### SSL Certificate
- Ensure your domain has a valid SSL certificate
- Stripe requires HTTPS for all webhook endpoints

### Domain Verification
1. Add your domain in Stripe Dashboard
2. Verify domain ownership

### Security Checklist
- [ ] Use environment variables for all keys
- [ ] Never commit keys to version control
- [ ] Enable webhook signature verification
- [ ] Implement proper error handling
- [ ] Set up monitoring and alerts
- [ ] Configure rate limiting

## 7. Marketplace Configuration

### Application Fees
Set your marketplace fee structure:
```python
# In your payment processing
application_fee = int(total_amount * STRIPE_APPLICATION_FEE_PERCENT / 100)
```

### Payment Holds
Configure 30-day holds for returns:
```python
# Payments are held automatically in our system
# Sellers receive payment after 30 days or when order is confirmed
hold_until = timezone.now() + timedelta(days=PAYMENT_HOLD_DAYS)
```

## 8. Monitoring and Maintenance

### Dashboard Monitoring
- Monitor payment success rates
- Track dispute rates
- Review payout schedules
- Monitor webhook delivery

### Regular Tasks
- Update Stripe library regularly
- Review and update webhook events
- Monitor for new Stripe features
- Update test card numbers if deprecated

## 9. Common Issues and Solutions

### Webhook Signature Verification Fails
- Check webhook secret in environment variables
- Ensure raw request body is used for verification
- Verify endpoint URL is correct

### Test Payments Not Working
- Confirm using test API keys
- Check test card numbers are correct
- Ensure webhook endpoints are accessible

### Connect Account Issues
- Verify Express accounts are enabled
- Check redirect URLs are configured
- Ensure proper account linking

## 10. Support and Resources

### Documentation
- [Stripe API Documentation](https://stripe.com/docs/api)
- [Stripe Connect Guide](https://stripe.com/docs/connect)
- [Webhook Documentation](https://stripe.com/docs/webhooks)

### Support
- Stripe Support: Available in dashboard
- Community: Stripe Discord/Stack Overflow
- Status Page: [status.stripe.com](https://status.stripe.com)

## Security Best Practices

1. **Never expose secret keys** in client-side code
2. **Validate webhook signatures** to ensure requests are from Stripe
3. **Use HTTPS everywhere** for payment-related endpoints
4. **Implement proper error handling** without exposing sensitive information
5. **Monitor for suspicious activity** through Stripe Dashboard
6. **Keep Stripe libraries updated** for security patches
7. **Use strong authentication** for admin access
8. **Implement proper logging** for audit trails

---

## Next Steps
After completing this setup, proceed to the [Payment System Documentation](./payments/payment-system.md) to understand how the 30-day hold system works.