# Stripe Test Scripts

This directory contains scripts for creating and managing Stripe test connected accounts for comprehensive payout testing.

## Scripts Overview

### `create_test_connected_accounts.py`

**Purpose**: Creates multiple Stripe connected accounts with different IBAN configurations to test various payout scenarios.

**Features**:
- ✅ Creates 6 different test connected accounts with specific behaviors
- ✅ Configures Portuguese (PT) IBANs for EUR currency testing
- ✅ Comprehensive error handling and detailed logging
- ✅ Account validation and status verification
- ✅ JSON output for integration with Django tests
- ✅ Security safeguards (test-only API keys)

## Setup Requirements

### 1. Install Dependencies
```bash
pip install stripe python-dotenv
```

### 2. Environment Configuration
Ensure your `.env` file contains:
```env
STRIPE_SECRET_KEY=sk_test_your_test_key_here
```

⚠️ **Security**: This script only works with test API keys (starting with `sk_test_`)

### 3. Run the Script
```bash
cd /path/to/payment_system/tests/stripe
python create_test_connected_accounts.py
```

## Test Account Behaviors

The script creates accounts with these specific test behaviors:

| IBAN | Expected Behavior | Use Case |
|------|------------------|----------|
| `PT50000201231234567890154` | ✅ Payout succeeds | Standard success scenario |
| `PT23000201231234567890155` | ❌ Payout fails - no_account | Account not found |
| `PT89370400440532013002` | ❌ Payout fails - account_closed | Closed bank account |
| `PT05000201230000002222227` | ❌ Payout fails - insufficient_funds | Insufficient funds |
| `PT89370400440532013004` | ❌ Payout fails - debit_not_authorized | Authorization issues |
| `PT89370400440532013005` | ❌ Payout fails - invalid_currency | Currency mismatch |

## Output Files

### `created_accounts.json`
Contains complete details of all created accounts:
```json
{
  "created_at": "2024-01-15T10:30:00",
  "total_accounts": 6,
  "successful_accounts": 6,
  "accounts": [
    {
      "account_id": "acct_test123...",
      "iban": "PT50000201231234567890154",
      "external_account_id": "ba_test456...",
      "description": "Payout succeeds - Standard success case",
      "expected_behavior": "success",
      "currency": "eur",
      "email": "test-0154@designia-testing.com",
      "status": true,
      "payouts_enabled": true,
      "details_submitted": true,
      "created_at": "2024-01-15T10:30:00"
    }
  ]
}
```

## Integration with Django

### Using in Django Tests
```python
import json
import os

# Load created accounts
accounts_file = os.path.join(settings.BASE_DIR, 'payment_system/tests/stripe/created_accounts.json')
with open(accounts_file, 'r') as f:
    test_accounts = json.load(f)

# Use in tests
success_account = next(a for a in test_accounts['accounts'] if a['expected_behavior'] == 'success')
failure_account = next(a for a in test_accounts['accounts'] if a['expected_behavior'] == 'failure_no_account')

# Test successful payout
stripe.Transfer.create(
    amount=1000,  # €10.00
    currency='eur',
    destination=success_account['account_id']
)
```

### Using in Payment Views
```python
from django.conf import settings
import json

def get_test_connected_account(behavior_type='success'):
    """Get a test connected account by behavior type."""
    accounts_file = os.path.join(
        settings.BASE_DIR,
        'payment_system/tests/stripe/created_accounts.json'
    )

    with open(accounts_file, 'r') as f:
        data = json.load(f)

    for account in data['accounts']:
        if account and account['expected_behavior'] == behavior_type:
            return account['account_id']

    return None

# Usage in views
test_account_id = get_test_connected_account('success')
if test_account_id:
    # Use for testing transfers
    pass
```

## Script Features

### Security Features
- ✅ **Test-only mode**: Only accepts test API keys
- ✅ **Environment validation**: Checks for required environment variables
- ✅ **Input validation**: Validates all inputs before API calls
- ✅ **Error boundaries**: Comprehensive exception handling

### Logging & Monitoring
- ✅ **Timestamped logs**: All operations logged with timestamps
- ✅ **Detailed error messages**: Specific error types and codes
- ✅ **Progress tracking**: Real-time creation progress
- ✅ **Verification steps**: Account validation after creation

### Account Configuration
- ✅ **Portuguese setup**: Configured for PT country and EUR currency
- ✅ **Individual accounts**: Business type set to individual
- ✅ **Required capabilities**: Transfers and card payments enabled
- ✅ **Compliance**: ToS acceptance and required fields completed

## Usage Scenarios

### 1. Testing Successful Payouts
```python
# Use account with IBAN ending in 0154
success_account_id = "acct_test_success..."
stripe.Transfer.create(
    amount=5000,  # €50.00
    currency='eur',
    destination=success_account_id
)
```

### 2. Testing Payout Failures
```python
# Use account with IBAN ending in 0155 (no_account error)
failure_account_id = "acct_test_failure..."
try:
    stripe.Transfer.create(
        amount=5000,
        currency='eur',
        destination=failure_account_id
    )
except stripe.error.InvalidRequestError as e:
    # Handle expected failure
    assert 'no_account' in str(e)
```

### 3. End-to-End Testing
```python
def test_all_payout_scenarios():
    """Test all possible payout outcomes."""
    with open('created_accounts.json', 'r') as f:
        accounts = json.load(f)

    for account in accounts['accounts']:
        if not account:
            continue

        test_payout_scenario(
            account['account_id'],
            account['expected_behavior']
        )
```

## Maintenance

### Cleaning Up Test Accounts
```python
import stripe

# Delete test accounts when done
for account_id in test_account_ids:
    try:
        stripe.Account.delete(account_id)
        print(f"Deleted account: {account_id}")
    except Exception as e:
        print(f"Failed to delete {account_id}: {e}")
```

### Re-running Scripts
- Safe to run multiple times
- Creates fresh accounts each time
- Previous accounts remain unless manually deleted
- Check Stripe dashboard for accumulated test accounts

## Troubleshooting

### Common Issues

1. **API Key Not Found**
   ```
   ERROR: STRIPE_SECRET_KEY not found in environment variables
   ```
   - Add `STRIPE_SECRET_KEY=sk_test_...` to your `.env` file

2. **Production Key Error**
   ```
   ERROR: Not a test API key!
   ```
   - Ensure you're using a test key starting with `sk_test_`

3. **Account Creation Failures**
   ```
   Stripe error: The country PT is not currently supported
   ```
   - Verify your Stripe account supports Portugal
   - Check if test mode supports PT country

4. **External Account Errors**
   ```
   Failed to attach bank account
   ```
   - IBAN format might be invalid
   - Check country/currency compatibility

### Debug Mode
For additional debugging, modify the script:
```python
# Add at top of script
import logging
logging.basicConfig(level=logging.DEBUG)
stripe.log = 'debug'
```

## Security Notes

⚠️ **Important Security Reminders**:
- Only use test API keys (never production keys)
- Test accounts don't handle real money
- Clean up test accounts after testing
- Don't commit API keys to version control
- Use environment variables for configuration

## Support

For issues with this script:
1. Check the logs for specific error messages
2. Verify your Stripe account settings
3. Ensure test mode is enabled
4. Review the troubleshooting section above

---

**Created for**: Designia Payment System Testing
**Last Updated**: 2024-01-15
**Dependencies**: stripe, python-dotenv
**Python Version**: 3.7+
