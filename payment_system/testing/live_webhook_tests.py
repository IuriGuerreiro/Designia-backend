#!/usr/bin/env python
"""
Live webhook testing with Stripe CLI integration
"""
import os
import sys
import time
import json
import signal
import subprocess
import requests
from datetime import datetime

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# Set Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'designiaBackend.settings')

import django
django.setup()

from payment_system.models import WebhookEvent, Payment
from marketplace.models import Order
from django.contrib.auth import get_user_model

User = get_user_model()


class LiveWebhookTester:
    """Test webhooks with real Stripe CLI integration"""
    
    def __init__(self):
        self.webhook_url = 'http://localhost:8000/api/payments/webhooks/stripe/'
        self.webhook_process = None
        self.test_results = []
    
    def setup_webhook_forwarding(self):
        """Start Stripe CLI webhook forwarding"""
        print("🚀 Starting webhook forwarding...")
        
        try:
            # Start webhook forwarding in background
            self.webhook_process = subprocess.Popen([
                'stripe', 'listen', 
                '--forward-to', self.webhook_url,
                '--print-secret'
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # Wait a moment for the process to start
            time.sleep(3)
            
            if self.webhook_process.poll() is None:
                print(f"✅ Webhook forwarding active: {self.webhook_url}")
                return True
            else:
                print("❌ Failed to start webhook forwarding")
                return False
                
        except Exception as e:
            print(f"❌ Error setting up webhook forwarding: {e}")
            return False
    
    def cleanup_webhook_forwarding(self):
        """Stop webhook forwarding"""
        if self.webhook_process:
            print("🛑 Stopping webhook forwarding...")
            self.webhook_process.terminate()
            self.webhook_process.wait()
    
    def trigger_webhook(self, event_type, description=""):
        """Trigger a webhook event using Stripe CLI"""
        print(f"🎯 Triggering {event_type}...")
        
        try:
            result = subprocess.run([
                'stripe', 'trigger', event_type
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                print(f"✅ {event_type} triggered successfully")
                if description:
                    print(f"   Description: {description}")
                return True
            else:
                print(f"❌ Failed to trigger {event_type}: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"❌ Error triggering {event_type}: {e}")
            return False
    
    def check_webhook_received(self, event_type, timeout=10):
        """Check if webhook was received and processed"""
        print(f"⏳ Waiting for {event_type} webhook...")
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            # Check if webhook event was logged
            recent_events = WebhookEvent.objects.filter(
                event_type=event_type,
                created_at__gte=datetime.now().replace(second=0, microsecond=0)
            ).order_by('-created_at')
            
            if recent_events.exists():
                event = recent_events.first()
                print(f"✅ Webhook received: {event.stripe_event_id}")
                print(f"   Status: {event.status}")
                print(f"   Processing attempts: {event.processing_attempts}")
                return True, event
            
            time.sleep(1)
        
        print(f"❌ Webhook {event_type} not received within {timeout}s")
        return False, None
    
    def test_webhook_endpoint_health(self):
        """Test webhook endpoint is accessible"""
        print("🏥 Testing webhook endpoint health...")
        
        try:
            response = requests.get('http://localhost:8000/api/payments/webhooks/stripe/')
            if response.status_code in [405, 400]:  # Method not allowed or bad request is expected
                print("✅ Webhook endpoint is accessible")
                return True
            else:
                print(f"⚠️ Unexpected response: {response.status_code}")
                return False
        except requests.exceptions.ConnectionError:
            print("❌ Django server not accessible. Make sure server is running.")
            return False
        except Exception as e:
            print(f"❌ Error testing endpoint: {e}")
            return False
    
    def run_payment_webhook_test(self):
        """Test payment_intent.succeeded webhook"""
        print("\\n🧪 Testing Payment Intent Succeeded Webhook")
        print("=" * 50)
        
        # Trigger the webhook
        if not self.trigger_webhook('payment_intent.succeeded', 
                                   "Tests payment processing completion"):
            return False
        
        # Wait for webhook to be received
        received, event = self.check_webhook_received('payment_intent.succeeded')
        
        if received:
            self.test_results.append({
                'test': 'payment_intent.succeeded',
                'status': 'PASSED',
                'event_id': event.stripe_event_id
            })
            return True
        else:
            self.test_results.append({
                'test': 'payment_intent.succeeded',
                'status': 'FAILED',
                'error': 'Webhook not received'
            })
            return False
    
    def run_payment_failed_webhook_test(self):
        """Test payment_intent.payment_failed webhook"""
        print("\\n🧪 Testing Payment Intent Failed Webhook")
        print("=" * 50)
        
        if not self.trigger_webhook('payment_intent.payment_failed',
                                   "Tests payment failure handling"):
            return False
        
        received, event = self.check_webhook_received('payment_intent.payment_failed')
        
        if received:
            self.test_results.append({
                'test': 'payment_intent.payment_failed',
                'status': 'PASSED',
                'event_id': event.stripe_event_id
            })
            return True
        else:
            self.test_results.append({
                'test': 'payment_intent.payment_failed',
                'status': 'FAILED',
                'error': 'Webhook not received'
            })
            return False
    
    def run_account_webhook_test(self):
        """Test account.updated webhook"""
        print("\\n🧪 Testing Account Updated Webhook")
        print("=" * 50)
        
        if not self.trigger_webhook('account.updated',
                                   "Tests seller account status updates"):
            return False
        
        received, event = self.check_webhook_received('account.updated')
        
        if received:
            self.test_results.append({
                'test': 'account.updated',
                'status': 'PASSED',
                'event_id': event.stripe_event_id
            })
            return True
        else:
            self.test_results.append({
                'test': 'account.updated',
                'status': 'FAILED',
                'error': 'Webhook not received'
            })
            return False
    
    def run_transfer_webhook_test(self):
        """Test transfer.created webhook"""
        print("\\n🧪 Testing Transfer Created Webhook")
        print("=" * 50)
        
        if not self.trigger_webhook('transfer.created',
                                   "Tests seller payout processing"):
            return False
        
        received, event = self.check_webhook_received('transfer.created')
        
        if received:
            self.test_results.append({
                'test': 'transfer.created',
                'status': 'PASSED',
                'event_id': event.stripe_event_id
            })
            return True
        else:
            self.test_results.append({
                'test': 'transfer.created',
                'status': 'FAILED',
                'error': 'Webhook not received'
            })
            return False
    
    def print_test_summary(self):
        """Print comprehensive test results"""
        print("\\n" + "=" * 60)
        print("🏁 LIVE WEBHOOK TEST RESULTS")
        print("=" * 60)
        
        passed = len([r for r in self.test_results if r['status'] == 'PASSED'])
        total = len(self.test_results)
        
        print(f"📊 Overall: {passed}/{total} tests passed")
        print()
        
        for result in self.test_results:
            status_icon = "✅" if result['status'] == 'PASSED' else "❌"
            print(f"{status_icon} {result['test']}")
            
            if result['status'] == 'PASSED':
                print(f"   Event ID: {result['event_id']}")
            else:
                print(f"   Error: {result['error']}")
            print()
        
        # Database state
        print("📊 Database State:")
        print(f"   Webhook events logged: {WebhookEvent.objects.count()}")
        print(f"   Recent events (last hour): {WebhookEvent.objects.filter(created_at__gte=datetime.now().replace(minute=0, second=0, microsecond=0)).count()}")
        print()
        
        if passed == total:
            print("🎉 ALL WEBHOOK TESTS PASSED!")
        else:
            print(f"⚠️  {total - passed} tests failed - check Django server logs")
    
    def run_all_tests(self):
        """Run complete webhook test suite"""
        print("🧪 LIVE WEBHOOK TESTING SUITE")
        print("=" * 60)
        print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        # Test endpoint health
        if not self.test_webhook_endpoint_health():
            print("❌ Cannot proceed - Django server not accessible")
            return
        
        # Setup webhook forwarding
        if not self.setup_webhook_forwarding():
            print("❌ Cannot proceed - webhook forwarding failed")
            return
        
        try:
            # Wait for webhook forwarding to be ready
            print("⏳ Waiting for webhook forwarding to initialize...")
            time.sleep(5)
            
            # Run all webhook tests
            self.run_payment_webhook_test()
            time.sleep(2)  # Small delay between tests
            
            self.run_payment_failed_webhook_test()
            time.sleep(2)
            
            self.run_account_webhook_test()
            time.sleep(2)
            
            self.run_transfer_webhook_test()
            
        finally:
            # Cleanup
            self.cleanup_webhook_forwarding()
        
        # Print results
        self.print_test_summary()


def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    print('\\n🛑 Interrupting tests...')
    sys.exit(0)


if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    
    tester = LiveWebhookTester()
    tester.run_all_tests()