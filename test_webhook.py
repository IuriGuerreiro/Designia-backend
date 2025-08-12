#!/usr/bin/env python
"""
Simple test script to verify webhook endpoint is accessible
Run this after starting your Django server to test webhook connectivity
"""

import requests
import json

def test_webhook_endpoint():
    """Test that webhook endpoint is accessible"""
    
    # Test webhook endpoint (this should return 400 because we don't have proper Stripe signature)
    webhook_url = "http://localhost:8000/api/payments/stripe_webhook/"
    
    # Test payload (minimal)
    test_payload = {
        "id": "evt_test_webhook",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_session",
                "metadata": {
                    "user_id": "1",
                    "cart_id": "1"
                }
            }
        }
    }
    
    try:
        print("🧪 Testing webhook endpoint...")
        response = requests.post(
            webhook_url,
            json=test_payload,
            headers={"Content-Type": "application/json"}
        )
        
        print(f"📡 Response Status: {response.status_code}")
        print(f"📨 Response Text: {response.text}")
        
        # We expect 400 because we don't have proper Stripe signature
        if response.status_code == 400 and "signature" in response.text.lower():
            print("✅ Webhook endpoint is accessible and properly validating signatures")
            return True
        elif response.status_code == 400 and "webhook secret not configured" in response.text:
            print("⚠️ Webhook endpoint accessible but STRIPE_WEBHOOK_SECRET not set")
            print("💡 Add STRIPE_WEBHOOK_SECRET to your .env file")
            return True
        else:
            print(f"❌ Unexpected response: {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to Django server")
        print("💡 Make sure Django server is running on http://localhost:8000")
        return False
    except Exception as e:
        print(f"❌ Error testing webhook: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Webhook Test Script")
    print("=" * 50)
    
    success = test_webhook_endpoint()
    
    print("\n" + "=" * 50)
    if success:
        print("✅ Webhook setup test completed successfully")
        print("\n📋 Next steps:")
        print("1. Set up webhook in Stripe Dashboard")
        print("2. Add STRIPE_WEBHOOK_SECRET to .env file")
        print("3. Test with a real payment")
    else:
        print("❌ Webhook test failed")
        print("\n🛠️ Troubleshooting:")
        print("1. Check Django server is running")
        print("2. Verify URL routing is correct")
        print("3. Check for any server errors")