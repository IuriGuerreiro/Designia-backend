#!/usr/bin/env python
"""
Check webhook events received by Django server
"""
import os
import sys
from datetime import datetime, timedelta

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# Set Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "designiaBackend.settings")

import django

django.setup()

from payment_system.models import WebhookEvent


def check_recent_webhooks():
    """Check for webhook events in the last 10 minutes"""
    print("🔍 Checking for recent webhook events...")
    print("=" * 50)

    # Get events from last 10 minutes
    since = datetime.now() - timedelta(minutes=10)
    recent_events = WebhookEvent.objects.filter(created_at__gte=since).order_by("-created_at")

    if recent_events.exists():
        print(f"  Found {recent_events.count()} recent webhook event(s):")
        print()

        for event in recent_events:
            print(f"📧 Event ID: {event.stripe_event_id}")
            print(f"   Type: {event.event_type}")
            print(f"   Status: {event.status}")
            print(f"   Attempts: {event.processing_attempts}")
            print(f"   Created: {event.created_at}")
            if event.error_message:
                print(f"   Error: {event.error_message}")
            print()
    else:
        print(" No recent webhook events found")

        # Check all webhook events
        all_events = WebhookEvent.objects.all().order_by("-created_at")
        if all_events.exists():
            print(f"📊 Total webhook events in database: {all_events.count()}")
            latest = all_events.first()
            print(f"   Latest event: {latest.event_type} at {latest.created_at}")
        else:
            print("📊 No webhook events in database")

    print()
    print("💡 If no events found, check:")
    print("   - Django server is running on port 8000")
    print("   - Stripe CLI webhook forwarding is active")
    print("   - Webhook endpoint is accessible")


if __name__ == "__main__":
    check_recent_webhooks()
# ruff: noqa: E402
