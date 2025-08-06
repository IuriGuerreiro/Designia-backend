from django.test import TestCase
from django.contrib.auth import get_user_model
from marketplace.models import Product, Category, ProductMetrics
from .models import UserClick, ActivitySummary
from datetime import date, datetime

User = get_user_model()


class UserClickModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        self.category = Category.objects.create(
            name='Test Category',
            slug='test-category'
        )
        
        self.product = Product.objects.create(
            name='Test Product',
            slug='test-product',
            description='A test product',
            seller=self.user,
            category=self.category,
            price=99.99,
            stock_quantity=10
        )
    
    def test_track_activity_creates_click_record(self):
        """Test that track_activity creates a UserClick record"""
        activity = UserClick.track_activity(
            product=self.product,
            action='view',
            user=self.user
        )
        
        self.assertIsInstance(activity, UserClick)
        self.assertEqual(activity.product, self.product)
        self.assertEqual(activity.action, 'view')
        self.assertEqual(activity.user, self.user)
    
    def test_track_activity_updates_product_metrics(self):
        """Test that track_activity updates ProductMetrics"""
        # Track a view
        UserClick.track_activity(
            product=self.product,
            action='view',
            user=self.user
        )
        
        # Check that metrics were created and updated
        metrics = ProductMetrics.objects.get(product=self.product)
        self.assertEqual(metrics.total_views, 1)
        self.assertEqual(metrics.total_clicks, 0)
        
        # Track a click
        UserClick.track_activity(
            product=self.product,
            action='click',
            user=self.user
        )
        
        metrics.refresh_from_db()
        self.assertEqual(metrics.total_views, 1)
        self.assertEqual(metrics.total_clicks, 1)
    
    def test_track_activity_for_anonymous_user(self):
        """Test tracking activity for anonymous users with session key"""
        activity = UserClick.track_activity(
            product=self.product,
            action='view',
            session_key='anonymous_session_123'
        )
        
        self.assertIsNone(activity.user)
        self.assertEqual(activity.session_key, 'anonymous_session_123')
    
    def test_favorite_unfavorite_updates_metrics_correctly(self):
        """Test that favorite/unfavorite actions update metrics correctly"""
        metrics = ProductMetrics.objects.create(product=self.product)
        
        # Add favorite
        UserClick.track_activity(
            product=self.product,
            action='favorite',
            user=self.user
        )
        
        metrics.refresh_from_db()
        self.assertEqual(metrics.total_favorites, 1)
        
        # Remove favorite
        UserClick.track_activity(
            product=self.product,
            action='unfavorite',
            user=self.user
        )
        
        metrics.refresh_from_db()
        self.assertEqual(metrics.total_favorites, 0)
        
        # Ensure it doesn't go below 0
        UserClick.track_activity(
            product=self.product,
            action='unfavorite',
            user=self.user
        )
        
        metrics.refresh_from_db()
        self.assertEqual(metrics.total_favorites, 0)


class ActivitySummaryModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        self.category = Category.objects.create(
            name='Test Category',
            slug='test-category'
        )
        
        self.product = Product.objects.create(
            name='Test Product',
            slug='test-product',
            description='A test product',
            seller=self.user,
            category=self.category,
            price=99.99,
            stock_quantity=10
        )
    
    def test_generate_daily_summary(self):
        """Test generating daily activity summary"""
        # Create some activities for today
        today = date.today()
        UserClick.objects.create(
            product=self.product,
            action='view',
            user=self.user
        )
        UserClick.objects.create(
            product=self.product,
            action='click',
            user=self.user
        )
        UserClick.objects.create(
            product=self.product,
            action='favorite',
            session_key='anonymous_123'
        )
        
        # Generate summary
        summary = ActivitySummary.generate_daily_summary(self.product, today)
        
        self.assertEqual(summary.product, self.product)
        self.assertEqual(summary.period_type, 'daily')
        self.assertEqual(summary.total_views, 1)
        self.assertEqual(summary.total_clicks, 1)
        self.assertEqual(summary.total_favorites, 1)
        self.assertEqual(summary.unique_users, 1)
        self.assertEqual(summary.unique_sessions, 1)