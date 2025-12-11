#!/usr/bin/env python
"""
Manual webhook testing by sending HTTP requests directly
"""

import hashlib
import hmac
import json
import os
import sys
import time
from datetime import datetime

import requests


# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# Set Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "designiaBackend.settings")

import django


django.setup()

from payment_system.models import WebhookEvent


def create_stripe_signature(payload, secret):
    """Create a Stripe webhook signature for testing"""
    timestamp = int(time.time())
    signed_payload = f"{timestamp}.{payload}"
    signature = hmac.new(secret.encode("utf-8"), signed_payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={signature}"


def send_test_webhook(event_type, data):
    """Send a test webhook to our Django server"""
    webhook_url = "http://localhost:8000/api/payments/webhooks/stripe/"
    webhook_secret = "whsec_test_secret"  # Test secret

    # Create webhook payload
    payload = {
        "id": f"evt_test_{int(time.time())}",
        "object": "event",
        "api_version": "2020-08-27",
        "created": int(time.time()),
        "data": {"object": data},
        "livemode": False,
        "pending_webhooks": 1,
        "request": {"id": f"req_test_{int(time.time())}"},
        "type": event_type,
    }

    payload_json = json.dumps(payload, separators=(",", ":"))
    signature = create_stripe_signature(payload_json, webhook_secret)

    headers = {
        "Content-Type": "application/json",
        "Stripe-Signature": signature,
        "User-Agent": "Stripe/1.0 (+https://stripe.com/docs/webhooks)",
    }

    print(f"🚀 Sending {event_type} webhook...")
    print(f"   Event ID: {payload['id']}")

    try:
        response = requests.post(webhook_url, data=payload_json, headers=headers, timeout=10)
        print(f"   Response: {response.status_code}")

        if response.status_code == 200:
            print("  Webhook sent successfully")

            # Wait a moment and check if it was logged
            time.sleep(1)
            webhook_event = WebhookEvent.objects.filter(stripe_event_id=payload["id"]).first()

            if webhook_event:
                print("  Webhook logged in database")
                print(f"   Status: {webhook_event.status}")
                print(f"   Processing attempts: {webhook_event.processing_attempts}")
                return True
            else:
                print("⚠️ Webhook not found in database")
                return False
        else:
            print(f" Webhook failed: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False

    except Exception as e:
        print(f" Error sending webhook: {e}")
        return False


def test_payment_intent_succeeded():
    """Test payment_intent.succeeded webhook"""
    print("\\n🧪 Testing payment_intent.succeeded")
    print("-" * 40)

    data = {
        "id": "pi_test_manual_123",
        "object": "payment_intent",
        "amount": 10000,
        "currency": "usd",
        "status": "succeeded",
        "metadata": {"order_id": "test-order-123", "buyer_id": "test-buyer-123"},
    }

    return send_test_webhook("payment_intent.succeeded", data)


def test_payment_intent_failed():
    """Test payment_intent.payment_failed webhook"""
    print("\\n🧪 Testing payment_intent.payment_failed")
    print("-" * 40)

    data = {
        "id": "pi_test_manual_456",
        "object": "payment_intent",
        "amount": 5000,
        "currency": "usd",
        "status": "requires_payment_method",
        "last_payment_error": {
            "code": "card_declined",
            "decline_code": "generic_decline",
            "message": "Your card was declined.",
        },
    }

    return send_test_webhook("payment_intent.payment_failed", data)


def test_unknown_event():
    """Test unknown event type"""
    print("\\n🧪 Testing unknown event type")
    print("-" * 40)

    data = {"id": "test_object_123", "object": "test_object"}

    return send_test_webhook("test.unknown_event", data)


def run_manual_webhook_tests():
    """Run all manual webhook tests"""
    print("🧪 MANUAL WEBHOOK TESTING")
    print("=" * 50)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    results = []

    # Test various webhook types
    results.append(("payment_intent.succeeded", test_payment_intent_succeeded()))
    time.sleep(1)

    results.append(("payment_intent.payment_failed", test_payment_intent_failed()))
    time.sleep(1)

    results.append(("unknown_event", test_unknown_event()))

    # Print summary
    print("\\n" + "=" * 50)
    print("📊 TEST RESULTS")
    print("=" * 50)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    print(f"Overall: {passed}/{total} tests passed")
    print()

    for test_name, result in results:
        status_icon = " " if result else "❌"
        print(f"{status_icon} {test_name}")

    print()

    # Show database state
    total_events = WebhookEvent.objects.count()
    recent_events = WebhookEvent.objects.filter(
        created_at__gte=datetime.now().replace(minute=0, second=0, microsecond=0)
    ).count()

    print("📊 Database state:")
    print(f"   Total webhook events: {total_events}")
    print(f"   Events this hour: {recent_events}")

    if passed == total:
        print("\\n🎉 ALL MANUAL WEBHOOK TESTS PASSED!")
    else:
        print(f"\\n⚠️ {total - passed} tests failed")


if __name__ == "__main__":
    run_manual_webhook_tests()
# ruff: noqa: E402
