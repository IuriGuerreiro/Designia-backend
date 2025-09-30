# Payment System Comprehensive Test Suite

A complete testing system for the payment_system Django app with full endpoint coverage, security testing, and error handling validation.

## 📋 Test Coverage

### Endpoints Tested

1. **Checkout Endpoints**
   - `POST /api/payments/checkout_session/` - Create checkout session
   - `GET /api/payments/checkout_session/retry/<order_id>/` - Retry failed checkout

2. **Stripe Connect Endpoints**
   - `POST /api/payments/stripe/account/` - Create Stripe account
   - `POST /api/payments/stripe/create-session/` - Create account session
   - `GET /api/payments/stripe/account-status/` - Get account status

3. **Payment Holds Endpoints**
   - `GET /api/payments/stripe/holds/` - Get seller payment holds

4. **Payout Endpoints**
   - `POST /api/payments/payout/` - Create seller payout
   - `GET /api/payments/payouts/` - List user payouts
   - `GET /api/payments/payouts/<payout_id>/` - Get payout details
   - `GET /api/payments/payouts/<payout_id>/orders/` - Get payout orders

5. **Admin Endpoints**
   - `GET /api/payments/admin/payouts/` - List all payouts (admin only)
   - `GET /api/payments/admin/transactions/` - List all transactions (admin only)

### Test Categories

1. **Endpoint Tests** - Test all API endpoints with valid requests
2. **Authentication Tests** - Verify authentication requirements
3. **Permission Tests** - Test role-based access control
4. **Security Tests** - Validate security measures and database role verification
5. **Edge Case Tests** - Test error handling, invalid inputs, and edge cases
6. **Admin Tests** - Comprehensive admin endpoint testing

## 🚀 Quick Start

### Prerequisites

```bash
# Install required packages
pip install django djangorestframework djangorestframework-simplejwt stripe coverage
```

### Running Tests

#### Run All Tests
```bash
cd /path/to/Designia-backend
python payment_system/tests/run_all_tests.py
```

#### Run Specific Test Suite
```bash
# The script will prompt you to select:
# 1. All Tests (Comprehensive)
# 2. Endpoint Tests Only
# 3. Security Tests Only
# 4. Admin Tests Only
# 5. Payout Tests Only
# 6. Edge Case Tests Only
```

#### Run with Django Test Command
```bash
# All payment system tests
python manage.py test payment_system.tests.test_all_endpoints

# Specific test class
python manage.py test payment_system.tests.test_all_endpoints.AdminPayoutEndpointTests

# Specific test method
python manage.py test payment_system.tests.test_all_endpoints.AdminPayoutEndpointTests.test_admin_list_all_payouts_success
```

### Running with Coverage

```bash
# Install coverage
pip install coverage

# Run with coverage
coverage run --source='payment_system' manage.py test payment_system.tests.test_all_endpoints

# View coverage report
coverage report

# Generate HTML coverage report
coverage html
# Open htmlcov/index.html in browser
```

## 📊 Test Reports

### JSON Reports

Test reports are automatically generated in:
```
payment_system/tests/reports/test_report_YYYYMMDD_HHMMSS.json
```

Report includes:
- Timestamp
- Duration
- Summary (total, passed, failed, errors, skipped)
- Detailed failure and error information

### Coverage Reports

HTML coverage reports are generated in:
```
payment_system/tests/coverage_html/index.html
```

## 🔐 Security Testing

### Key Security Tests

1. **Database Role Verification**
   - Tests that user roles are ALWAYS fetched from database
   - Never trust JWT token claims for authorization
   - Validates the "never trust the token" principle

2. **Cross-Seller Access Prevention**
   - Sellers cannot access other sellers' data
   - Proper ownership validation on all endpoints

3. **Admin Access Control**
   - Admin endpoints require admin role from database
   - Non-admin users are properly rejected

4. **SQL Injection Prevention**
   - Tests malicious input handling
   - Validates Django ORM protection

## 📝 Test Structure

### Test Data Factory

The `TestDataFactory` class provides helper methods to create test data:

```python
factory = TestDataFactory()

# Create users
admin = factory.create_admin()
seller = factory.create_seller()
buyer = factory.create_buyer()

# Create products and orders
product = factory.create_product(seller)
order = factory.create_order(buyer, seller, product)

# Create transactions and payouts
transaction = factory.create_payment_transaction(seller, buyer, order)
payout = factory.create_payout(seller)
```

### Base Test Case

All test classes inherit from `BaseAuthTestCase` which provides:

```python
class MyTests(BaseAuthTestCase):
    def test_something(self):
        # Authenticate as different users
        self.authenticate_buyer()
        self.authenticate_seller()
        self.authenticate_admin()
        self.unauthenticate()
```

## 🧪 Test Examples

### Testing Admin Endpoints

```python
def test_admin_list_all_payouts_success(self):
    """Test admin can list all payouts"""
    self.authenticate_admin()
    url = reverse('payment_system:admin_list_all_payouts')

    response = self.client.get(url)
    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertIn('payouts', response.data)
```

### Testing Permission Denial

```python
def test_admin_list_payouts_non_admin(self):
    """Test non-admin cannot list all payouts"""
    self.authenticate_seller()
    url = reverse('payment_system:admin_list_all_payouts')

    response = self.client.get(url)
    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    self.assertIn('ADMIN_ACCESS_REQUIRED', response.data['error'])
```

### Testing Security

```python
def test_role_verification_from_database(self):
    """Test that role is always verified from database"""
    self.authenticate_seller()

    # Change role in database
    self.seller.role = 'user'
    self.seller.save()

    # Request should fail because DB role is now 'user'
    url = reverse('payment_system:get_seller_payment_holds')
    response = self.client.get(url)

    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
```

## 🎯 Expected Test Results

### Success Criteria

- **All endpoint tests pass**: All API endpoints return expected responses
- **Authentication enforced**: Unauthenticated requests properly rejected
- **Permissions validated**: Role-based access control works correctly
- **Security tests pass**: Database role verification and cross-seller protection work
- **Error handling works**: Invalid inputs and edge cases handled gracefully

### Typical Test Run

```
Test Summary:
✓ Checkout Endpoint Tests: 3/3 passed
✓ Stripe Connect Tests: 4/4 passed
✓ Payment Holds Tests: 4/4 passed
✓ Payout Tests: 8/8 passed
✓ Admin Endpoint Tests: 12/12 passed
✓ Security Tests: 5/5 passed
✓ Edge Case Tests: 7/7 passed

Total: 43 tests passed in 12.5 seconds
```

## 🐛 Troubleshooting

### Common Issues

1. **Import Errors**
   ```bash
   # Make sure you're in the project root
   cd /path/to/Designia-backend
   export DJANGO_SETTINGS_MODULE=Designia.settings
   ```

2. **Database Errors**
   ```bash
   # Create test database
   python manage.py migrate --database=test
   ```

3. **Stripe Mock Errors**
   ```bash
   # Tests use mocked Stripe API calls
   # No actual Stripe account needed for tests
   ```

## 📈 Coverage Goals

- **Endpoint Coverage**: 100% of payment_system endpoints
- **Line Coverage**: Target >80% for payment_system app
- **Branch Coverage**: Target >70% for critical paths
- **Security Coverage**: 100% of permission checks

## 🔄 Continuous Integration

### GitHub Actions Example

```yaml
name: Payment System Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: 3.11
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install coverage
      - name: Run tests
        run: |
          cd Designia-backend
          python payment_system/tests/run_all_tests.py
```

## 📚 Additional Resources

- [Django Testing Documentation](https://docs.djangoproject.com/en/stable/topics/testing/)
- [DRF Testing Guide](https://www.django-rest-framework.org/api-guide/testing/)
- [Coverage.py Documentation](https://coverage.readthedocs.io/)

## 🤝 Contributing

When adding new endpoints or features:

1. Add corresponding tests in `test_all_endpoints.py`
2. Run the full test suite to ensure nothing breaks
3. Aim for >80% coverage on new code
4. Include security tests for permission-based endpoints

## 📞 Support

For issues or questions about the testing system, contact the development team or create an issue in the repository.