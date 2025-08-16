# Portuguese Connected Account Testing Scripts

This directory contains scripts to create and test pre-verified Portuguese Stripe connected accounts for development and testing purposes.

## 🇵🇹 Scripts Overview

### 1. `create_test_connected_account.py`
**Purpose**: Creates a single pre-verified Portuguese Stripe connected account with all verification information pre-filled.

**Features**:
- ✅ Creates custom Stripe account for Portugal (PT)
- ✅ Pre-fills all individual verification information
- ✅ Sets up EUR banking with test IBAN
- ✅ Enables card payments, transfers, and SEPA debit
- ✅ Creates corresponding Django user
- ✅ Prevents duplicate account creation
- ✅ Tests transfer capability

### 2. Django Management Command
**Purpose**: Same functionality as above but integrated with Django's management system.

**Location**: `payment_system/management/commands/create_test_portugal_account.py`

### 3. `test_portugal_transfers.py`
**Purpose**: Comprehensive test suite to verify the Portuguese account and transfer functionality.

**Features**:
- ✅ Tests account status and capabilities
- ✅ Tests direct Stripe transfers
- ✅ Tests payment service transfers
- ✅ Tests full payment workflow with mock transactions

## 🚀 Usage Instructions

### Method 1: Direct Script Execution

```bash
# Navigate to the backend directory
cd /path/to/Designia-backend

# Run the account creation script
python payment_system/tests/create_test_connected_account.py

# Run the test suite
python payment_system/tests/test_portugal_transfers.py
```

### Method 2: Django Management Command

```bash
# Create account with basic setup
python manage.py create_test_portugal_account

# Create account and test transfers
python manage.py create_test_portugal_account --test-transfer

# Force creation even if account exists
python manage.py create_test_portugal_account --force
```

### Method 3: Virtual Environment

```bash
# Activate virtual environment first
source venv/bin/activate

# Then run any of the above commands
python payment_system/tests/create_test_connected_account.py
```

## 📊 Created Account Details

When the script runs successfully, it creates:

### Stripe Connected Account
- **Country**: Portugal (PT)
- **Type**: Custom account
- **Currency**: EUR
- **Capabilities**: Card payments, Transfers, SEPA debit payments

### Individual Information
- **Name**: Maria Silva
- **Email**: maria.silva@example.com
- **Phone**: +351210000000
- **DOB**: January 1, 1980
- **Address**: Rua Augusta 10, Lisbon, 1100-053, PT
- **Tax ID**: 00000000 (Portuguese NIF)

### Banking Information
- **Test IBAN**: PT50000201231234567890154
- **Account Holder**: Maria Silva
- **Type**: Individual

### Django User
- **Username**: portugal_seller
- **Email**: portugal-seller@example.com
- **Password**: TestPassword123!
- **2FA**: Enabled (required for sellers)
- **Stripe Account ID**: Automatically linked

## 🧪 Testing Workflow

### 1. Create Account
```bash
python manage.py create_test_portugal_account --test-transfer
```

### 2. Verify Account
```bash
python payment_system/tests/test_portugal_transfers.py
```

### 3. Test Frontend Integration
1. Login to your React app with:
   - Email: `portugal-seller@example.com`
   - Password: `TestPassword123!`
2. Navigate to `/stripe-holds` page
3. Create mock payment holds for testing
4. Test the transfer button functionality

## 🔧 Configuration Requirements

### Environment Variables
Ensure these are set in your Django settings:
- `STRIPE_SECRET_KEY`: Your Stripe test secret key
- `STRIPE_PUBLISHABLE_KEY`: Your Stripe test publishable key

### Django Settings
The scripts require:
- Proper Django setup with authentication app
- PaymentTransaction model
- User model with stripe_account_id field

## 🚨 Important Notes

### Test Mode Only
- These scripts are for **test mode only**
- Use Stripe test keys, never production keys
- Test accounts are automatically verified

### Single Account Creation
- Scripts prevent duplicate creation
- Use `--force` flag to override existing accounts
- Each run creates only 1 account to avoid confusion

### Currency Handling
- Portuguese account uses **EUR currency**
- Test transfers are in EUR (cents)
- Example: 1000 = €10.00

## 💡 Troubleshooting

### Common Issues

#### "Stripe API key not found"
```bash
# Check your Django settings
python manage.py shell -c "from django.conf import settings; print(settings.STRIPE_SECRET_KEY[:10])"
```

#### "Account already exists"
```bash
# Use force flag to recreate
python manage.py create_test_portugal_account --force
```

#### "User already exists"
```bash
# Delete existing user in Django admin or shell
python manage.py shell -c "from django.contrib.auth import get_user_model; User = get_user_model(); User.objects.filter(email='portugal-seller@example.com').delete()"
```

#### Transfer tests fail
1. Verify account capabilities are active
2. Check Stripe dashboard for any restrictions
3. Ensure sufficient balance in your test account

### Debug Mode
Add debug logging to see detailed Stripe responses:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 📋 Test Checklist

After running the scripts, verify:

- [ ] ✅ Stripe account created with Portuguese details
- [ ] ✅ Account capabilities are active (card_payments, transfers)
- [ ] ✅ Django user created with correct Stripe account ID
- [ ] ✅ Test transfers work (direct and via service)
- [ ] ✅ Mock payment transaction can be created
- [ ] ✅ Full workflow from hold to release works
- [ ] ✅ Frontend transfer button appears for ready payments
- [ ] ✅ Transfer API endpoint responds correctly

## 🔗 Related Files

### Backend Files
- `payment_system/models.py` - PaymentTransaction model
- `payment_system/views.py` - transfer_payment_to_seller endpoint
- `payment_system/stripe_service.py` - create_transfer_to_connected_account function
- `payment_system/urls.py` - Transfer endpoint routing

### Frontend Files
- `src/pages/StripeHolds.tsx` - Transfer button UI
- `src/services/paymentService.ts` - Transfer API call
- `src/config/api.ts` - API endpoint configuration

## 📞 Support

If you encounter issues:
1. Check the Django logs for detailed error messages
2. Verify Stripe dashboard for account status
3. Ensure all environment variables are set correctly
4. Check that Django models are properly migrated

---

**🎯 Goal**: These scripts enable rapid setup of a fully functional Portuguese test environment for developing and testing international payment transfers with Stripe Connect.