#!/bin/bash

# Payment System Test Runner Script
# Quick script to run all payment system tests

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Payment System Test Suite${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if we're in the right directory
if [ ! -f "manage.py" ]; then
    echo -e "${RED}Error: manage.py not found${NC}"
    echo -e "${YELLOW}Please run this script from the Django project root:${NC}"
    echo -e "${YELLOW}cd /path/to/Designia-backend && ./payment_system/tests/run_tests.sh${NC}"
    exit 1
fi

# Check if virtual environment is activated
if [ -z "$VIRTUAL_ENV" ]; then
    echo -e "${YELLOW}Warning: No virtual environment detected${NC}"
    echo -e "${YELLOW}Consider activating your virtual environment first${NC}"
    read -p "Continue anyway? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Parse command line arguments
TEST_SUITE="all"
WITH_COVERAGE=false
VERBOSITY=2

while [[ $# -gt 0 ]]; do
    case $1 in
        --suite)
            TEST_SUITE="$2"
            shift 2
            ;;
        --coverage)
            WITH_COVERAGE=true
            shift
            ;;
        --verbose)
            VERBOSITY=3
            shift
            ;;
        --help)
            echo "Usage: ./run_tests.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --suite <name>    Run specific test suite (all|endpoints|security|admin|payout|edge)"
            echo "  --coverage        Run with coverage analysis"
            echo "  --verbose         Increase output verbosity"
            echo "  --help            Show this help message"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Define test patterns
case $TEST_SUITE in
    "all")
        TEST_PATTERN="payment_system.tests.test_all_endpoints"
        ;;
    "endpoints")
        TEST_PATTERN="payment_system.tests.test_all_endpoints.CheckoutEndpointTests payment_system.tests.test_all_endpoints.StripeConnectEndpointTests payment_system.tests.test_all_endpoints.PaymentHoldsEndpointTests payment_system.tests.test_all_endpoints.PayoutEndpointTests"
        ;;
    "security")
        TEST_PATTERN="payment_system.tests.test_all_endpoints.SecurityAndPermissionTests"
        ;;
    "admin")
        TEST_PATTERN="payment_system.tests.test_all_endpoints.AdminPayoutEndpointTests"
        ;;
    "payout")
        TEST_PATTERN="payment_system.tests.test_all_endpoints.PayoutEndpointTests"
        ;;
    "edge")
        TEST_PATTERN="payment_system.tests.test_all_endpoints.EdgeCaseAndErrorHandlingTests"
        ;;
    *)
        echo -e "${RED}Unknown test suite: $TEST_SUITE${NC}"
        echo "Valid suites: all, endpoints, security, admin, payout, edge"
        exit 1
        ;;
esac

echo -e "${GREEN}Running test suite: $TEST_SUITE${NC}"
echo ""

# Run tests with or without coverage
if [ "$WITH_COVERAGE" = true ]; then
    echo -e "${BLUE}Running with coverage analysis...${NC}"
    echo ""

    # Check if coverage is installed
    if ! python -c "import coverage" 2>/dev/null; then
        echo -e "${RED}Coverage module not installed${NC}"
        echo -e "${YELLOW}Install it with: pip install coverage${NC}"
        exit 1
    fi

    # Run with coverage
    coverage run --source='payment_system' manage.py test $TEST_PATTERN --verbosity=$VERBOSITY

    # Show coverage report
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}Coverage Report${NC}"
    echo -e "${BLUE}========================================${NC}"
    coverage report

    # Generate HTML report
    coverage html
    HTML_DIR="htmlcov"
    if [ -d "$HTML_DIR" ]; then
        echo ""
        echo -e "${GREEN}HTML coverage report generated: ${HTML_DIR}/index.html${NC}"
    fi
else
    # Run without coverage
    python manage.py test $TEST_PATTERN --verbosity=$VERBOSITY
fi

# Capture exit code
EXIT_CODE=$?

# Print final status
echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}✓ All tests passed!${NC}"
    echo -e "${GREEN}========================================${NC}"
else
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}✗ Some tests failed${NC}"
    echo -e "${RED}========================================${NC}"
fi

exit $EXIT_CODE
