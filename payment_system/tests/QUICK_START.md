# Quick Start Guide - Payment System Tests

## 🚀 Run Tests in 3 Steps

### Step 1: Navigate to Project Root
```bash
cd /mnt/f/Nigger/Projects/Programmes/WebApps/Desginia/Designia-backend
```

### Step 2: Run Tests
```bash
# Option A: Using the Python script (Recommended)
python payment_system/tests/run_all_tests.py

# Option B: Using the bash script
./payment_system/tests/run_tests.sh

# Option C: Using Django's test command
python manage.py test payment_system.tests.test_all_endpoints
```

### Step 3: View Results
Results will be displayed in the terminal with color-coded output.

---

## 📊 Run with Coverage

```bash
# Install coverage first
pip install coverage

# Run with coverage
./payment_system/tests/run_tests.sh --coverage

# Or with Python script (includes coverage if installed)
python payment_system/tests/run_all_tests.py
```

---

## 🎯 Run Specific Test Suites

### All Admin Tests
```bash
python manage.py test payment_system.tests.test_all_endpoints.AdminPayoutEndpointTests
```

### All Security Tests
```bash
python manage.py test payment_system.tests.test_all_endpoints.SecurityAndPermissionTests
```

### All Payout Tests
```bash
python manage.py test payment_system.tests.test_all_endpoints.PayoutEndpointTests
```

### All Edge Case Tests
```bash
python manage.py test payment_system.tests.test_all_endpoints.EdgeCaseAndErrorHandlingTests
```

### Single Test Method
```bash
python manage.py test payment_system.tests.test_all_endpoints.AdminPayoutEndpointTests.test_admin_list_all_payouts_success
```

---

## 🧪 What Gets Tested

### ✅ All Endpoints (18 endpoints)
- Checkout session creation
- Stripe Connect account management
- Payment holds retrieval
- Payout creation and management
- Admin oversight (payouts & transactions)

### ✅ Authentication & Permissions
- JWT authentication required
- Role-based access control (seller, admin, user)
- Database role verification (never trust tokens)

### ✅ Security
- Cross-seller access prevention
- SQL injection prevention
- Database role verification
- Admin access control

### ✅ Error Handling
- Invalid UUIDs
- Malformed JSON
- Missing required fields
- Negative/zero amounts
- Edge cases

---

## 📈 Expected Output

```
========================================
PAYMENT SYSTEM COMPREHENSIVE TEST SUITE
========================================

Running 43 tests...

✓ test_admin_list_all_payouts_success
✓ test_admin_list_all_transactions_success
✓ test_admin_list_payouts_non_admin
✓ test_create_checkout_session_success
...

========================================
TEST SUMMARY
========================================
Total Tests Run: 43
✓ Passed: 43
✗ Failed: 0
⚠ Errors: 0
⊘ Skipped: 0
Duration: 12.5 seconds
========================================

📄 Test report generated: payment_system/tests/reports/test_report_20250129_143052.json
```

---

## 🔧 Troubleshooting

### "Module not found" error
```bash
# Make sure you're in the project root
cd /mnt/f/Nigger/Projects/Programmes/WebApps/Desginia/Designia-backend

# Check Django settings
export DJANGO_SETTINGS_MODULE=Designia.settings
```

### "Database error"
```bash
# Run migrations
python manage.py migrate
```

### "Import error: stripe"
```bash
# Install required packages
pip install stripe djangorestframework djangorestframework-simplejwt
```

---

## 📊 Coverage Report

After running with coverage:

```bash
# View HTML report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
start htmlcov/index.html  # Windows
```

---

## 🎯 Test Goals

- **100%** endpoint coverage
- **>80%** line coverage for payment_system
- **100%** security test coverage
- **0** failing tests in CI/CD

---

## 📝 Next Steps

1. ✅ Run all tests to verify system health
2. ✅ Check coverage report for gaps
3. ✅ Add tests for new endpoints when adding features
4. ✅ Run tests before every commit
5. ✅ Include in CI/CD pipeline

---

## 🚨 Critical Tests

These tests MUST pass:

- `test_role_verification_from_database` - Security
- `test_admin_list_payouts_non_admin` - Permission
- `test_cross_seller_access_prevention` - Security
- `test_sql_injection_prevention` - Security

---

## 💡 Tips

1. **Run tests frequently** - Catch issues early
2. **Use coverage** - Find untested code
3. **Read failures carefully** - Error messages are detailed
4. **Test new features** - Add tests when adding endpoints
5. **Keep tests fast** - Mock external APIs (Stripe)

---

## 📞 Need Help?

See the full documentation: `payment_system/tests/README_TESTING.md`