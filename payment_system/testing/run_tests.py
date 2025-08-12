#!/usr/bin/env python
"""
Comprehensive test runner for payment system with coverage reporting
"""
import os
import sys
import subprocess
import time
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Set Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'designiaBackend.settings')

import django
from django.test.utils import get_runner
from django.conf import settings


class PaymentSystemTestRunner:
    """Comprehensive test runner for payment system"""
    
    def __init__(self):
        self.project_root = project_root
        self.test_modules = [
            'payment_system.testing.test_models',
            'payment_system.testing.test_views',
            'payment_system.testing.test_end_to_end',
            'payment_system.testing.test_webhooks'
        ]
        self.coverage_enabled = self.check_coverage_available()
    
    def check_coverage_available(self):
        """Check if coverage.py is available"""
        try:
            import coverage
            return True
        except ImportError:
            return False
    
    def install_test_dependencies(self):
        """Install required testing dependencies"""
        dependencies = [
            'coverage',
            'pytest',
            'pytest-django',
            'pytest-cov',
            'factory-boy'  # For test data generation
        ]
        
        print("📦 Installing test dependencies...")
        for dep in dependencies:
            try:
                subprocess.run(
                    [sys.executable, '-m', 'pip', 'install', dep],
                    check=True,
                    capture_output=True
                )
                print(f"✅ Installed {dep}")
            except subprocess.CalledProcessError as e:
                print(f"⚠️ Failed to install {dep}: {e}")
        
        print("Dependencies installation complete!")
    
    def run_django_setup(self):
        """Initialize Django for testing"""
        django.setup()
        print("✅ Django initialized for testing")
    
    def run_unit_tests(self, verbosity=2):
        """Run unit tests for models"""
        print("\n🧪 Running Unit Tests (Models)")
        print("=" * 50)
        
        TestRunner = get_runner(settings)
        test_runner = TestRunner(verbosity=verbosity, interactive=False)
        
        failures = test_runner.run_tests(['payment_system.testing.test_models'])
        
        if failures:
            print("❌ Unit tests failed")
            return False
        else:
            print("✅ Unit tests passed")
            return True
    
    def run_integration_tests(self, verbosity=2):
        """Run integration tests for views/APIs"""
        print("\n🔗 Running Integration Tests (Views/APIs)")
        print("=" * 50)
        
        TestRunner = get_runner(settings)
        test_runner = TestRunner(verbosity=verbosity, interactive=False)
        
        failures = test_runner.run_tests(['payment_system.testing.test_views'])
        
        if failures:
            print("❌ Integration tests failed")
            return False
        else:
            print("✅ Integration tests passed")
            return True
    
    def run_e2e_tests(self, verbosity=2):
        """Run end-to-end tests"""
        print("\n🌐 Running End-to-End Tests")
        print("=" * 50)
        
        TestRunner = get_runner(settings)
        test_runner = TestRunner(verbosity=verbosity, interactive=False)
        
        failures = test_runner.run_tests(['payment_system.testing.test_end_to_end'])
        
        if failures:
            print("❌ End-to-end tests failed")
            return False
        else:
            print("✅ End-to-end tests passed")
            return True
    
    def run_webhook_tests(self, verbosity=2):
        """Run webhook tests"""
        print("\n🪝 Running Webhook Tests")
        print("=" * 50)
        
        TestRunner = get_runner(settings)
        test_runner = TestRunner(verbosity=verbosity, interactive=False)
        
        failures = test_runner.run_tests(['payment_system.testing.test_webhooks'])
        
        if failures:
            print("❌ Webhook tests failed")
            return False
        else:
            print("✅ Webhook tests passed")
            return True
    
    def run_all_tests(self, verbosity=2):
        """Run all payment system tests"""
        print("\n🎯 Running All Payment System Tests")
        print("=" * 60)
        
        TestRunner = get_runner(settings)
        test_runner = TestRunner(verbosity=verbosity, interactive=False)
        
        failures = test_runner.run_tests(self.test_modules)
        
        if failures:
            print("❌ Some tests failed")
            return False
        else:
            print("✅ All tests passed")
            return True
    
    def run_with_coverage(self, verbosity=2):
        """Run tests with coverage reporting"""
        if not self.coverage_enabled:
            print("⚠️ Coverage not available, installing...")
            self.install_test_dependencies()
        
        print("\n📊 Running Tests with Coverage")
        print("=" * 50)
        
        try:
            import coverage
            
            # Initialize coverage
            cov = coverage.Coverage(
                source=['payment_system'],
                omit=[
                    '*/tests/*',
                    '*/testing/*',
                    '*/migrations/*',
                    '*/venv/*',
                    '*/site-packages/*'
                ]
            )
            
            cov.start()
            
            # Run tests
            success = self.run_all_tests(verbosity)
            
            cov.stop()
            cov.save()
            
            # Generate coverage report
            print("\n📈 Coverage Report:")
            print("=" * 30)
            cov.report()
            
            # Generate HTML coverage report
            html_dir = self.project_root / 'htmlcov'
            cov.html_report(directory=str(html_dir))
            print(f"\n📊 HTML coverage report generated: {html_dir}/index.html")
            
            return success
            
        except ImportError:
            print("❌ Coverage.py not available")
            return self.run_all_tests(verbosity)
    
    def run_performance_tests(self):
        """Run performance benchmarks"""
        print("\n⚡ Running Performance Tests")
        print("=" * 50)
        
        try:
            from django.test import TestCase
            from django.contrib.auth import get_user_model
            from payment_system.models import Payment
            import time
            
            User = get_user_model()
            
            # Create test data
            print("Creating test data...")
            start_time = time.time()
            
            users = []
            for i in range(100):
                user = User.objects.create_user(
                    username=f'perf_user_{i}',
                    email=f'perf{i}@test.com'
                )
                users.append(user)
            
            creation_time = time.time() - start_time
            print(f"✅ Created 100 users in {creation_time:.2f} seconds")
            
            # Test bulk operations
            start_time = time.time()
            
            payments = Payment.objects.bulk_create([
                Payment(
                    payment_intent_id=f'pi_perf_test_{i}',
                    buyer=users[i % len(users)],
                    amount=50.00,
                    status='succeeded'
                )
                for i in range(1000)
            ])
            
            bulk_time = time.time() - start_time
            print(f"✅ Bulk created 1000 payments in {bulk_time:.2f} seconds")
            
            # Cleanup
            Payment.objects.filter(payment_intent_id__startswith='pi_perf_test_').delete()
            User.objects.filter(username__startswith='perf_user_').delete()
            
            print("🧹 Cleanup completed")
            return True
            
        except Exception as e:
            print(f"❌ Performance tests failed: {e}")
            return False
    
    def generate_test_report(self, results):
        """Generate comprehensive test report"""
        report_file = self.project_root / 'test_report.md'
        
        with open(report_file, 'w') as f:
            f.write("# Payment System Test Report\n\n")
            f.write(f"Generated on: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            f.write("## Test Results Summary\n\n")
            for test_type, result in results.items():
                status = "✅ PASSED" if result else "❌ FAILED"
                f.write(f"- **{test_type}**: {status}\n")
            
            f.write("\n## Test Categories\n\n")
            f.write("### Unit Tests\n")
            f.write("- Payment model validation\n")
            f.write("- 30-day hold system logic\n")
            f.write("- Seller payout calculations\n")
            f.write("- Refund request workflows\n\n")
            
            f.write("### Integration Tests\n")
            f.write("- Payment processing APIs\n")
            f.write("- Stripe account management\n")
            f.write("- Authentication and permissions\n")
            f.write("- Error handling\n\n")
            
            f.write("### End-to-End Tests\n")
            f.write("- Complete payment flows\n")
            f.write("- Multi-seller scenarios\n")
            f.write("- Security validations\n")
            f.write("- Performance benchmarks\n\n")
            
            f.write("### Webhook Tests\n")
            f.write("- Stripe CLI integration\n")
            f.write("- Event processing\n")
            f.write("- Error recovery\n")
            f.write("- Signature verification\n\n")
            
            f.write("## Coverage Information\n\n")
            if self.coverage_enabled:
                f.write("Coverage report available in `htmlcov/index.html`\n\n")
            else:
                f.write("Install `coverage` package for detailed coverage reporting\n\n")
            
            f.write("## Manual Testing\n\n")
            f.write("### Stripe CLI Setup\n")
            f.write("```bash\n")
            f.write("# Run the setup script\n")
            f.write("./payment_system/testing/stripe_cli_setup.sh\n")
            f.write("```\n\n")
            
            f.write("### Manual Test Commands\n")
            f.write("```bash\n")
            f.write("# Login to Stripe CLI\n")
            f.write("stripe login\n\n")
            f.write("# Forward webhooks\n")
            f.write("stripe listen --forward-to localhost:8000/api/payments/webhooks/stripe/\n\n")
            f.write("# Test payment success\n")
            f.write("stripe trigger payment_intent.succeeded\n")
            f.write("```\n\n")
        
        print(f"📄 Test report generated: {report_file}")
    
    def main(self):
        """Main test execution"""
        print("🚀 Payment System Comprehensive Testing")
        print("=" * 60)
        
        # Initialize Django
        self.run_django_setup()
        
        # Install dependencies if needed
        if '--install-deps' in sys.argv:
            self.install_test_dependencies()
        
        # Determine test mode
        test_mode = 'all'
        if '--unit' in sys.argv:
            test_mode = 'unit'
        elif '--integration' in sys.argv:
            test_mode = 'integration'
        elif '--e2e' in sys.argv:
            test_mode = 'e2e'
        elif '--webhooks' in sys.argv:
            test_mode = 'webhooks'
        elif '--coverage' in sys.argv:
            test_mode = 'coverage'
        elif '--performance' in sys.argv:
            test_mode = 'performance'
        
        verbosity = 2
        if '--quiet' in sys.argv:
            verbosity = 0
        elif '--verbose' in sys.argv:
            verbosity = 3
        
        results = {}
        success = True
        
        # Run tests based on mode
        if test_mode == 'unit':
            results['Unit Tests'] = self.run_unit_tests(verbosity)
        elif test_mode == 'integration':
            results['Integration Tests'] = self.run_integration_tests(verbosity)
        elif test_mode == 'e2e':
            results['End-to-End Tests'] = self.run_e2e_tests(verbosity)
        elif test_mode == 'webhooks':
            results['Webhook Tests'] = self.run_webhook_tests(verbosity)
        elif test_mode == 'coverage':
            results['All Tests with Coverage'] = self.run_with_coverage(verbosity)
        elif test_mode == 'performance':
            results['Performance Tests'] = self.run_performance_tests()
        else:
            # Run all tests
            results['Unit Tests'] = self.run_unit_tests(verbosity)
            results['Integration Tests'] = self.run_integration_tests(verbosity)
            results['End-to-End Tests'] = self.run_e2e_tests(verbosity)
            results['Webhook Tests'] = self.run_webhook_tests(verbosity)
            
            if '--with-performance' in sys.argv:
                results['Performance Tests'] = self.run_performance_tests()
        
        # Check overall success
        success = all(results.values())
        
        # Generate report
        self.generate_test_report(results)
        
        # Print summary
        print("\n" + "=" * 60)
        print("📋 TEST SUMMARY")
        print("=" * 60)
        
        for test_type, result in results.items():
            status = "✅ PASSED" if result else "❌ FAILED"
            print(f"{test_type}: {status}")
        
        overall_status = "✅ ALL TESTS PASSED" if success else "❌ SOME TESTS FAILED"
        print(f"\nOverall Result: {overall_status}")
        
        if not success:
            print("\n💡 Tips for fixing test failures:")
            print("- Check Django settings configuration")
            print("- Verify Stripe test keys are set")
            print("- Ensure database migrations are applied")
            print("- Check for missing test dependencies")
        
        print("\n📚 Additional Resources:")
        print("- Test report: test_report.md")
        if self.coverage_enabled:
            print("- Coverage report: htmlcov/index.html")
        print("- Stripe CLI setup: payment_system/testing/stripe_cli_setup.sh")
        
        return 0 if success else 1


def print_usage():
    """Print usage information"""
    print("Usage: python run_tests.py [OPTIONS]")
    print("\nTest Modes:")
    print("  --unit          Run only unit tests")
    print("  --integration   Run only integration tests")
    print("  --e2e           Run only end-to-end tests")
    print("  --webhooks      Run only webhook tests")
    print("  --coverage      Run all tests with coverage")
    print("  --performance   Run only performance tests")
    print("\nOptions:")
    print("  --install-deps  Install test dependencies")
    print("  --with-performance  Include performance tests in full run")
    print("  --quiet         Minimal output")
    print("  --verbose       Verbose output")
    print("  --help          Show this help message")


if __name__ == '__main__':
    if '--help' in sys.argv:
        print_usage()
        sys.exit(0)
    
    runner = PaymentSystemTestRunner()
    exit_code = runner.main()
    sys.exit(exit_code)