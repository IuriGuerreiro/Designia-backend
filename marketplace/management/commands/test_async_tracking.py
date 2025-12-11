"""
Management command to test the async tracking system.

Usage:
    python manage.py test_async_tracking
    python manage.py test_async_tracking --status
"""

import time

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from marketplace.async_tracking import AsyncTracker
from marketplace.models import Product


User = get_user_model()


class Command(BaseCommand):
    help = "Test the async tracking system performance and functionality"

    def add_arguments(self, parser):
        parser.add_argument(
            "--status",
            action="store_true",
            help="Show async tracking system status",
        )
        parser.add_argument(
            "--load-test",
            action="store_true",
            help="Run a load test with multiple tracking requests",
        )
        parser.add_argument(
            "--count",
            type=int,
            default=100,
            help="Number of tracking requests to queue for load test (default: 100)",
        )

    def handle(self, *args, **options):
        if options["status"]:
            self.show_status()
        elif options["load_test"]:
            self.run_load_test(options["count"])
        else:
            self.run_basic_test()

    def show_status(self):
        """Show the current status of the async tracking system."""
        self.stdout.write(self.style.SUCCESS("🔍 Async Tracking System Status"))
        self.stdout.write("=" * 50)

        try:
            status = AsyncTracker.get_queue_status()

            self.stdout.write(f"Queue Size: {status.get('queue_size', 'Unknown')}")
            self.stdout.write(f"Thread Pool Active: {status.get('thread_pool_active', False)}")
            self.stdout.write(f"Processor Thread Alive: {status.get('processor_thread_alive', False)}")
            self.stdout.write(f"Processor Thread Name: {status.get('processor_thread_name', 'Unknown')}")

            if "error" in status:
                self.stdout.write(self.style.ERROR(f" Error: {status['error']}"))
            else:
                self.stdout.write(self.style.SUCCESS("  System appears to be running normally"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f" Failed to get status: {str(e)}"))

    def run_basic_test(self):
        """Run basic functionality tests."""
        self.stdout.write(self.style.SUCCESS("🧪 Running Basic Async Tracking Tests"))
        self.stdout.write("=" * 50)

        try:
            # Initialize the system
            AsyncTracker.initialize()
            self.stdout.write("  AsyncTracker initialized")

            # Get a test product
            product = Product.objects.filter(is_active=True).first()
            if not product:
                self.stdout.write(self.style.ERROR(" No active products found for testing"))
                return

            self.stdout.write(f"📦 Using test product: {product.name}")

            # Get a test user
            user = User.objects.first()
            if user:
                self.stdout.write(f"👤 Using test user: {user.username}")
            else:
                self.stdout.write("⚠️  No users found - testing anonymous tracking only")

            # Test different tracking types
            test_cases = [
                ("listing_view", lambda: self.test_listing_view([product])),
                ("product_click", lambda: self.test_product_click(product, user)),
                ("cart_action", lambda: self.test_cart_action(product, user)),
                ("favorite_action", lambda: self.test_favorite_action(product, user)),
            ]

            for test_name, test_func in test_cases:
                try:
                    self.stdout.write(f"\n🧪 Testing {test_name}...")
                    result = test_func()
                    if result:
                        self.stdout.write(self.style.SUCCESS(f"  {test_name} test passed"))
                    else:
                        self.stdout.write(self.style.WARNING(f"⚠️  {test_name} test returned False"))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f" {test_name} test failed: {str(e)}"))

            # Wait a moment for processing
            self.stdout.write("\n⏳ Waiting 3 seconds for background processing...")
            time.sleep(3)

            # Show final status
            self.stdout.write("\n📊 Final Status:")
            self.show_status()

        except Exception as e:
            self.stdout.write(self.style.ERROR(f" Basic test failed: {str(e)}"))

    def run_load_test(self, count):
        """Run a load test with multiple tracking requests."""
        self.stdout.write(self.style.SUCCESS(f"🚀 Running Load Test ({count} requests)"))
        self.stdout.write("=" * 50)

        try:
            # Initialize the system
            AsyncTracker.initialize()

            # Get test data
            products = list(Product.objects.filter(is_active=True)[:10])
            if not products:
                self.stdout.write(self.style.ERROR(" No active products found for testing"))
                return

            users = list(User.objects.all()[:5])

            # Record start time
            start_time = time.time()

            # Queue many requests
            success_count = 0
            for i in range(count):
                product = products[i % len(products)]
                user = users[i % len(users)] if users else None

                # Alternate between different tracking types
                if i % 4 == 0:
                    result = AsyncTracker.queue_listing_view([product], None)
                elif i % 4 == 1 and user:
                    result = AsyncTracker.queue_cart_action(product, user, "cart_add", 1)
                elif i % 4 == 2 and user:
                    result = AsyncTracker.queue_favorite_action(product, user, "favorite")
                else:
                    result = AsyncTracker.queue_product_click(product, None)

                if result:
                    success_count += 1

            # Record end time
            end_time = time.time()
            queue_time = end_time - start_time

            self.stdout.write("📊 Queuing Results:")
            self.stdout.write(f"   Total Requests: {count}")
            self.stdout.write(f"   Successful: {success_count}")
            self.stdout.write(f"   Failed: {count - success_count}")
            self.stdout.write(f"   Queue Time: {queue_time:.3f} seconds")
            self.stdout.write(f"   Requests/Second: {count / queue_time:.1f}")

            # Show queue status
            self.stdout.write("\n📊 Queue Status After Load:")
            self.show_status()

            # Wait for processing
            self.stdout.write("\n⏳ Waiting 10 seconds for background processing...")
            time.sleep(10)

            # Show final status
            self.stdout.write("\n📊 Final Status After Processing:")
            self.show_status()

        except Exception as e:
            self.stdout.write(self.style.ERROR(f" Load test failed: {str(e)}"))

    def test_listing_view(self, products):
        """Test listing view tracking."""

        # Mock request object (simplified)
        class MockRequest:
            def __init__(self):
                self.user = User.objects.first() or type("MockUser", (), {"is_authenticated": False})()
                self.session = type("MockSession", (), {"session_key": "test_session_123", "save": lambda: None})()
                self.META = {
                    "HTTP_USER_AGENT": "Test User Agent",
                    "REMOTE_ADDR": "127.0.0.1",
                    "HTTP_REFERER": "",
                }
                self.method = "GET"
                self.path = "/test/"

        mock_request = MockRequest()
        return AsyncTracker.queue_listing_view(products, mock_request)

    def test_product_click(self, product, user):
        """Test product click tracking."""
        if not user:
            return True  # Skip if no user available

        class MockRequest:
            def __init__(self, user):
                self.user = user
                self.session = type("MockSession", (), {"session_key": "test_session_123", "save": lambda: None})()
                self.META = {
                    "HTTP_USER_AGENT": "Test User Agent",
                    "REMOTE_ADDR": "127.0.0.1",
                    "HTTP_REFERER": "",
                }
                self.method = "GET"
                self.path = "/test/"

        mock_request = MockRequest(user)
        return AsyncTracker.queue_product_click(product, mock_request)

    def test_cart_action(self, product, user):
        """Test cart action tracking."""
        if not user:
            return True  # Skip if no user available

        return AsyncTracker.queue_cart_action(product, user, "cart_add", 2)

    def test_favorite_action(self, product, user):
        """Test favorite action tracking."""
        if not user:
            return True  # Skip if no user available

        return AsyncTracker.queue_favorite_action(product, user, "favorite")
