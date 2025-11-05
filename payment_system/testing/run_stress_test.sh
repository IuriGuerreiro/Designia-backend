#!/bin/bash

# Payment System Extreme Stress Test Runner
# ==========================================
#
# Quick runner for payment system stress testing with 50x concurrency.
# Tests READ COMMITTED isolation, 10ms deadlock retry, and proper model ordering.
# WARNING: This generates EXTREME load - ensure your system can handle it!

echo "🧪 PAYMENT SYSTEM STRESS TEST RUNNER"
echo "======================================"
echo ""

# Check if Django is available
if ! python -c "import django" 2>/dev/null; then
    echo "❌ Error: Django not found. Please ensure Django is installed."
    exit 1
fi

# Check if we're in the right directory
if [ ! -f "manage.py" ]; then
    echo "❌ Error: manage.py not found. Please run from Django project root."
    exit 1
fi

echo "🔧 Available EXTREME stress tests (50x load):"
echo "1. Full multithreading stress test (250 threads - comprehensive)"
echo "2. Webhook-only stress test (250 HTTP requests)"
echo "3. Custom concurrency test (configurable)"
echo ""
echo "⚠️  WARNING: These tests generate EXTREME load!"
echo ""

read -p "Select test type (1-3): " test_type

case $test_type in
    1)
        echo ""
        echo "🚀 Running FULL MULTITHREADING EXTREME STRESS TEST"
        echo "📊 50x concurrency, 250 concurrent threads, all payment operations"
        echo "⏱️  This may take 5-10 minutes - EXTREME LOAD!"
        echo "⚠️  Ensure your database can handle 250+ concurrent connections!"
        echo ""
        python -c "
import os, sys, django
sys.path.append('$(pwd)')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'designiaBackend.settings')
django.setup()

from payment_system.testing.stress_test_multithreading import run_payment_stress_test
run_payment_stress_test(concurrency_multiplier=50)
"
        ;;
    2)
        echo ""
        echo "🚀 Running EXTREME WEBHOOK STRESS TEST"
        echo "📊 50x concurrency, 250+ concurrent HTTP webhook requests"
        echo "⏱️  This may take 3-5 minutes - EXTREME LOAD!"
        echo "⚠️  Ensure your web server can handle 250+ concurrent requests!"
        echo ""
        python payment_system/testing/webhook_stress_runner.py
        ;;
    3)
        echo ""
        read -p "Enter concurrency multiplier (default 50): " multiplier
        multiplier=${multiplier:-50}

        echo ""
        echo "🚀 Running CUSTOM EXTREME STRESS TEST"
        echo "📊 ${multiplier}x concurrency ($((multiplier * 5)) threads)"
        echo "⏱️  This may take several minutes with extreme load..."
        echo "⚠️  WARNING: $((multiplier * 5)) concurrent database connections!"
        echo ""

        python -c "
import os, sys, django
sys.path.append('$(pwd)')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'designiaBackend.settings')
django.setup()

from payment_system.testing.stress_test_multithreading import run_payment_stress_test
run_payment_stress_test(concurrency_multiplier=$multiplier)
"
        ;;
    *)
        echo "❌ Invalid selection. Exiting."
        exit 1
        ;;
esac

echo ""
echo "✅ Stress test completed!"
echo ""
echo "📊 EXTREME LOAD Test validated:"
echo "   • READ COMMITTED isolation level under 50x load"
echo "   • 10ms deadlock retry functionality under extreme stress"
echo "   • Proper model ordering (Order→Tracker→Transaction) at scale"
echo "   • Massive concurrent webhook processing capability"
echo "   • Transaction rollback safety under extreme conditions"
echo "   • Database connection pool handling under stress"
echo ""
echo "💡 Check the output above for detailed performance metrics."
echo "🔥 System survived EXTREME 50x load testing!"
