# Payment System Endpoint Testing Guide

## Test Data Summary

All 41 payment system tests pass successfully (100% pass rate). Here's how to test the endpoints manually.

## Test Users

The test suite automatically creates these users:

| User Type | Email | Password | Role | Stripe Account |
|-----------|-------|----------|------|----------------|
| Seller | testseller@test.com | testpass123 | seller | acct_test_seller1 |
| Buyer | testbuyer@test.com | testpass123 | user | - |
| Admin | testadmin@test.com | testpass123 | admin | - |

## Authentication

First, get an authentication token:

```bash
# Login as seller
curl -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"testseller@test.com","password":"testpass123"}'

# Save the token from response
export TOKEN="your_token_here"
```

## Endpoint Testing

### 1. Stripe Connect Endpoints

####  Check Stripe Account Status
```bash
curl -X GET http://localhost:8000/payment_system/stripe/account-status/ \
  -H "Authorization: Bearer $TOKEN"
```

#### Create Stripe Account (if not exists)
```bash
curl -X POST http://localhost:8000/payment_system/stripe/account/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"country":"US","business_type":"individual"}'
```

#### Create Account Session (for onboarding)
```bash
curl -X POST http://localhost:8000/payment_system/stripe/create-session/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json"
```

### 2. Checkout Endpoints

#### Create Checkout Session
```bash
# First, add items to cart (marketplace endpoint)
curl -X POST http://localhost:8000/marketplace/cart/add/ \
  -H "Authorization: Bearer $BUYER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"product_id":"<product_uuid>","quantity":1}'

# Then create checkout session
curl -X POST http://localhost:8000/payment_system/checkout_session/ \
  -H "Authorization: Bearer $BUYER_TOKEN" \
  -H "Content-Type: application/json"
```

#### Retry Failed Checkout
```bash
curl -X GET http://localhost:8000/payment_system/checkout_session/retry/<order_uuid>/ \
  -H "Authorization: Bearer $BUYER_TOKEN"
```

### 3. Payout Endpoints (Seller)

#### Create Payout Request
```bash
curl -X POST http://localhost:8000/payment_system/payout/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"amount":100.00,"currency":"usd"}'
```

#### List Your Payouts
```bash
curl -X GET http://localhost:8000/payment_system/payouts/ \
  -H "Authorization: Bearer $TOKEN"
```

#### Get Payout Details
```bash
curl -X GET http://localhost:8000/payment_system/payouts/<payout_uuid>/ \
  -H "Authorization: Bearer $TOKEN"
```

#### Get Payout Orders
```bash
curl -X GET http://localhost:8000/payment_system/payouts/<payout_uuid>/orders/ \
  -H "Authorization: Bearer $TOKEN"
```

### 4. Admin Endpoints

```bash
# Login as admin first
curl -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"testadmin@test.com","password":"testpass123"}'

export ADMIN_TOKEN="admin_token_here"
```

#### List All Payouts (Admin)
```bash
curl -X GET http://localhost:8000/payment_system/admin/payouts/ \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# With filters
curl -X GET "http://localhost:8000/payment_system/admin/payouts/?status=paid&seller_id=<user_id>" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

#### List All Transactions (Admin)
```bash
curl -X GET http://localhost:8000/payment_system/admin/transactions/ \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# With filters
curl -X GET "http://localhost:8000/payment_system/admin/transactions/?status=succeeded&seller_id=<user_id>" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

## Creating Test Data

### Quick Test Data (Minimal)
```bash
python manage.py create_minimal_test_data
```
Creates 5 simple transactions for quick testing.

### Comprehensive Test Data (Recommended)
```bash
# Create 20 orders with transactions and payouts
python manage.py create_test_transactions --orders 20 --with-payouts

# Create 50 orders without payouts
python manage.py create_test_transactions --orders 50

# Clear existing data and create fresh data
python manage.py create_test_transactions --orders 30 --with-payouts --clear
```

**Options:**
- `--orders N`: Number of orders to create (default: 10)
- `--with-payouts`: Create payout records for completed transactions
- `--clear`: Clear existing test data before creating new data

**What gets created:**
- 3 test sellers with Stripe accounts
- 1 test buyer
- Random products across multiple categories
- Orders with various statuses (payment_confirmed, pending_payment, cancelled)
- Payment transactions for completed orders
- Payout records grouping multiple transactions (with --with-payouts)

## Running Automated Tests

### Run All Payment Tests
```bash
python manage.py test payment_system.tests.test_all_endpoints
```

### Run Specific Test Categories
```bash
# Checkout tests
python manage.py test payment_system.tests.test_all_endpoints.CheckoutEndpointTests

# Stripe Connect tests
python manage.py test payment_system.tests.test_all_endpoints.StripeConnectEndpointTests

# Payout tests
python manage.py test payment_system.tests.test_all_endpoints.PayoutEndpointTests

# Admin tests
python manage.py test payment_system.tests.test_all_endpoints.AdminPayoutEndpointTests

# Security tests
python manage.py test payment_system.tests.test_all_endpoints.SecurityValidationTests
```

### Run Individual Tests
```bash
python manage.py test payment_system.tests.test_all_endpoints.StripeConnectEndpointTests.test_create_stripe_account_success --verbosity=2
```

## Test Coverage Summary

✅ **100% Pass Rate (41/41 tests)**

### Test Categories:
- ✅ Checkout Tests (3/3) - Cart-based checkout sessions
- ✅ Stripe Connect Tests (4/4) - Account creation and management
- ✅ Payment Holds Tests (4/4) - Seller payment hold retrieval
- ✅ Payout Tests (7/7) - Payout creation, listing, details
- ✅ Admin Tests (10/10) - Admin oversight endpoints
- ✅ Security Tests (6/6) - Permission and authentication
- ✅ Edge Cases (7/7) - Error handling and validation

### Key Security Features Tested:
- ✅ Database role verification (never trust JWT tokens alone)
- ✅ Admin role validation
- ✅ Seller-specific access controls
- ✅ SQL injection prevention
- ✅ Authentication requirements
- ✅ Cross-seller data access prevention

## Common Testing Scenarios

### Scenario 1: Complete Purchase Flow
1. Create/login buyer account
2. Add products to cart
3. Create checkout session
4. (Simulated) Complete Stripe payment
5. Webhook processes payment
6. Transaction recorded for seller

### Scenario 2: Seller Payout Flow
1. Login as seller
2. Check available balance
3. Request payout
4. View payout status
5. Check payout details and included orders

### Scenario 3: Admin Oversight
1. Login as admin
2. View all payouts across sellers
3. Filter by status/seller/date
4. View all transactions
5. Monitor system health

## Stripe Test Mode

All tests use Stripe test mode with mock data. For real integration testing:

1. Set up Stripe test keys in `.env`
2. Use Stripe test card numbers
3. Monitor Stripe Dashboard (test mode)
4. Use Stripe CLI for webhook testing

## Notes

- All tests mock Stripe API calls to avoid real API usage
- Tests create isolated test database
- Each test is independent and cleans up after itself
- Security validations ensure production-ready code