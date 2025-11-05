#!/usr/bin/env python
"""
Comprehensive Test Runner for Payment System
Runs all tests with coverage reporting and detailed output
"""
import os
import sys
from pathlib import Path

import django

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

# Set Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Designia.settings")
django.setup()

import json
from datetime import datetime

from django.conf import settings
from django.test.runner import DiscoverRunner


class ColoredTestRunner(DiscoverRunner):
    """Enhanced test runner with colored output and detailed reporting"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.test_results = {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "start_time": None,
            "end_time": None,
            "failures": [],
            "errors_list": [],
        }

    def run_tests(self, test_labels, **kwargs):
        """Run tests and collect detailed results"""
        print("\n" + "=" * 80)
        print("PAYMENT SYSTEM COMPREHENSIVE TEST SUITE")
        print("=" * 80)
        print(f"Django Version: {django.get_version()}")
        print(f"Python Version: {sys.version.split()[0]}")
        print(f"Test Database: {settings.DATABASES['default']['ENGINE']}")
        print("=" * 80 + "\n")

        self.test_results["start_time"] = datetime.now()

        # Run the tests
        result = super().run_tests(test_labels, **kwargs)

        self.test_results["end_time"] = datetime.now()
        duration = (self.test_results["end_time"] - self.test_results["start_time"]).total_seconds()

        # Print summary
        print("\n" + "=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        print(f"Total Tests Run: {self.test_results['total']}")
        print(f"✓ Passed: {self.test_results['passed']}")
        print(f"✗ Failed: {self.test_results['failed']}")
        print(f"⚠ Errors: {self.test_results['errors']}")
        print(f"⊘ Skipped: {self.test_results['skipped']}")
        print(f"Duration: {duration:.2f} seconds")
        print("=" * 80 + "\n")

        if self.test_results["failures"]:
            print("\n" + "=" * 80)
            print("FAILED TESTS")
            print("=" * 80)
            for failure in self.test_results["failures"]:
                print(f"\n✗ {failure['test']}")
                print(f"   {failure['error']}")

        if self.test_results["errors_list"]:
            print("\n" + "=" * 80)
            print("ERRORS")
            print("=" * 80)
            for error in self.test_results["errors_list"]:
                print(f"\n⚠ {error['test']}")
                print(f"   {error['error']}")

        # Generate JSON report
        self.generate_json_report()

        return result

    def generate_json_report(self):
        """Generate JSON test report"""
        report_dir = project_root / "payment_system" / "tests" / "reports"
        report_dir.mkdir(exist_ok=True)

        report_file = report_dir / f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        report_data = {
            "timestamp": self.test_results["start_time"].isoformat(),
            "duration_seconds": (self.test_results["end_time"] - self.test_results["start_time"]).total_seconds(),
            "summary": {
                "total": self.test_results["total"],
                "passed": self.test_results["passed"],
                "failed": self.test_results["failed"],
                "errors": self.test_results["errors"],
                "skipped": self.test_results["skipped"],
            },
            "failures": self.test_results["failures"],
            "errors": self.test_results["errors_list"],
        }

        with open(report_file, "w") as f:
            json.dump(report_data, f, indent=2)

        print(f"\n📄 Test report generated: {report_file}")


def run_specific_test_suite():
    """Run specific test categories"""
    print("\n" + "=" * 80)
    print("TEST SUITE OPTIONS")
    print("=" * 80)
    print("1. All Tests (Comprehensive)")
    print("2. Endpoint Tests Only")
    print("3. Security Tests Only")
    print("4. Admin Tests Only")
    print("5. Payout Tests Only")
    print("6. Edge Case Tests Only")
    print("=" * 80)

    choice = input("\nSelect test suite (1-6) or press Enter for all: ").strip()

    test_patterns = {
        "1": ["payment_system.tests.test_all_endpoints"],
        "2": [
            "payment_system.tests.test_all_endpoints.CheckoutEndpointTests",
            "payment_system.tests.test_all_endpoints.StripeConnectEndpointTests",
            "payment_system.tests.test_all_endpoints.PaymentHoldsEndpointTests",
            "payment_system.tests.test_all_endpoints.PayoutEndpointTests",
        ],
        "3": ["payment_system.tests.test_all_endpoints.SecurityAndPermissionTests"],
        "4": ["payment_system.tests.test_all_endpoints.AdminPayoutEndpointTests"],
        "5": ["payment_system.tests.test_all_endpoints.PayoutEndpointTests"],
        "6": ["payment_system.tests.test_all_endpoints.EdgeCaseAndErrorHandlingTests"],
    }

    test_labels = test_patterns.get(choice, test_patterns["1"])
    return test_labels


def check_test_requirements():
    """Check if all test requirements are met"""
    print("\n🔍 Checking test environment...")

    requirements = {"Django": True, "Django REST Framework": True, "Stripe": False, "Test Database": True}

    try:
        import importlib.util

        requirements["Stripe"] = importlib.util.find_spec("stripe") is not None
    except Exception:
        pass

    all_met = all(requirements.values())

    if all_met:
        print("✓ All requirements met")
    else:
        print("⚠ Some requirements missing:")
        for req, met in requirements.items():
            if not met:
                print(f"  ✗ {req}")

    return all_met


def main():
    """Main test runner function"""
    print("\n" + "=" * 80)
    print("PAYMENT SYSTEM TEST SUITE")
    print("Comprehensive Testing System for All Endpoints")
    print("=" * 80)

    # Check requirements
    if not check_test_requirements():
        print("\n⚠ Warning: Some requirements are missing. Tests may fail.")
        response = input("Continue anyway? (y/n): ")
        if response.lower() != "y":
            print("Exiting...")
            return

    # Select test suite
    test_labels = run_specific_test_suite()

    # Run tests with coverage if available
    try:
        import coverage

        print("\n📊 Running tests with coverage analysis...")

        cov = coverage.Coverage(source=["payment_system"])
        cov.start()

        runner = ColoredTestRunner(verbosity=2, keepdb=False)
        failures = runner.run_tests(test_labels)

        cov.stop()
        cov.save()

        print("\n" + "=" * 80)
        print("COVERAGE REPORT")
        print("=" * 80)
        cov.report()

        # Generate HTML coverage report
        cov_dir = project_root / "payment_system" / "tests" / "coverage_html"
        cov.html_report(directory=str(cov_dir))
        print(f"\n📊 HTML coverage report: {cov_dir}/index.html")

    except ImportError:
        print("\n⚠ Coverage module not installed. Running tests without coverage...")
        print("Install coverage: pip install coverage")

        runner = ColoredTestRunner(verbosity=2, keepdb=False)
        failures = runner.run_tests(test_labels)

    # Exit with appropriate code
    sys.exit(bool(failures))


if __name__ == "__main__":
    main()
# ruff: noqa: E402
