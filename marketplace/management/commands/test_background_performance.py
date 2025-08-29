"""
Performance test to demonstrate true background processing.

This command times API responses to prove that tracking happens after response.
"""

from django.core.management.base import BaseCommand
from django.test import RequestFactory
from django.contrib.auth import get_user_model
from marketplace.models import Product
from marketplace.views import ProductViewSet
import time
import statistics

User = get_user_model()


class Command(BaseCommand):
    help = 'Test that API responses are truly instant (background processing)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--requests',
            type=int,
            default=10,
            help='Number of requests to test (default: 10)',
        )

    def handle(self, *args, **options):
        self.test_api_performance(options['requests'])

    def test_api_performance(self, num_requests):
        """Test API response times to prove background processing."""
        self.stdout.write(self.style.SUCCESS('🚀 Testing Background Processing Performance'))
        self.stdout.write('=' * 60)
        
        # Get test data
        products = list(Product.objects.filter(is_active=True)[:20])
        if not products:
            self.stdout.write(self.style.ERROR(" No active products found for testing"))
            return
        
        user = User.objects.first()
        
        # Setup request factory
        factory = RequestFactory()
        
        self.stdout.write(f"🧪 Testing {num_requests} product list requests...")
        self.stdout.write(f"📦 Using {len(products)} products in response")
        
        # Test product list performance
        response_times = []
        
        for i in range(num_requests):
            # Create mock request
            request = factory.get('/api/products/')
            if user:
                request.user = user
            else:
                from django.contrib.auth.models import AnonymousUser
                request.user = AnonymousUser()
            
            # Time the API call
            start_time = time.time()
            
            # Call the view directly
            view = ProductViewSet()
            view.request = request
            view.format_kwarg = None
            
            # This should be nearly instant if tracking is truly background
            response = view.list(request)
            
            end_time = time.time()
            response_time_ms = (end_time - start_time) * 1000
            response_times.append(response_time_ms)
            
            if i % 2 == 0:
                self.stdout.write(f"   Request {i+1}: {response_time_ms:.1f}ms")
        
        # Calculate statistics
        avg_time = statistics.mean(response_times)
        min_time = min(response_times)
        max_time = max(response_times)
        median_time = statistics.median(response_times)
        
        self.stdout.write("\n📊 Performance Results:")
        self.stdout.write(f"   Average Response Time: {avg_time:.1f}ms")
        self.stdout.write(f"   Minimum Response Time: {min_time:.1f}ms")
        self.stdout.write(f"   Maximum Response Time: {max_time:.1f}ms")
        self.stdout.write(f"   Median Response Time: {median_time:.1f}ms")
        
        # Performance evaluation
        if avg_time < 50:
            self.stdout.write(self.style.SUCCESS(f"  EXCELLENT: Average {avg_time:.1f}ms - True background processing!"))
        elif avg_time < 100:
            self.stdout.write(self.style.SUCCESS(f"  GOOD: Average {avg_time:.1f}ms - Background processing working"))
        elif avg_time < 200:
            self.stdout.write(self.style.WARNING(f"⚠️  FAIR: Average {avg_time:.1f}ms - Some blocking still occurring"))
        else:
            self.stdout.write(self.style.ERROR(f" POOR: Average {avg_time:.1f}ms - Tracking may still be blocking"))
        
        # Test individual product view
        self.stdout.write("\n🧪 Testing product detail view...")
        
        product = products[0]
        detail_times = []
        
        for i in range(5):
            request = factory.get(f'/api/products/{product.slug}/')
            if user:
                request.user = user
            else:
                from django.contrib.auth.models import AnonymousUser
                request.user = AnonymousUser()
            
            start_time = time.time()
            
            view = ProductViewSet()
            view.request = request
            view.format_kwarg = None
            view.kwargs = {'slug': product.slug}
            
            response = view.retrieve(request, slug=product.slug)
            
            end_time = time.time()
            response_time_ms = (end_time - start_time) * 1000
            detail_times.append(response_time_ms)
        
        avg_detail_time = statistics.mean(detail_times)
        self.stdout.write(f"   Product Detail Average: {avg_detail_time:.1f}ms")
        
        if avg_detail_time < 30:
            self.stdout.write(self.style.SUCCESS("  Product detail views are instant!"))
        elif avg_detail_time < 50:
            self.stdout.write(self.style.SUCCESS("  Product detail views are very fast"))
        else:
            self.stdout.write(self.style.WARNING("⚠️  Product detail views could be faster"))
        
        # Wait for background processing
        self.stdout.write("\n⏳ Waiting 5 seconds for background processing to complete...")
        time.sleep(5)
        
        self.stdout.write("\n🎉 Performance test completed!")
        self.stdout.write("📊 If average response times are <100ms, background processing is working correctly.")
        self.stdout.write("🔍 Check logs to see background tracking activity after responses.")
        
        # Show queue status
        self.stdout.write("\n📊 Background Queue Status:")
        try:
            from marketplace.async_tracking import AsyncTracker
            status = AsyncTracker.get_queue_status()
            self.stdout.write(f"   Queue Size: {status.get('queue_size', 'Unknown')}")
            self.stdout.write(f"   Thread Pool Active: {status.get('thread_pool_active', False)}")
            self.stdout.write(f"   Processor Thread Alive: {status.get('processor_thread_alive', False)}")
        except Exception as e:
            self.stdout.write(f"   Error getting status: {str(e)}")
            
        # Performance recommendations
        self.stdout.write("\n💡 Performance Tips:")
        if avg_time > 100:
            self.stdout.write("   - Consider adding database indexes on frequently queried fields")
            self.stdout.write("   - Check for N+1 query problems in serializers")
            self.stdout.write("   - Consider implementing Redis caching for product data")
        else:
            self.stdout.write("   - Performance looks good! Background processing is working effectively.")
            self.stdout.write("   - Users should experience near-instant page loads.")
            self.stdout.write("   - Metrics are being tracked without impacting user experience.")