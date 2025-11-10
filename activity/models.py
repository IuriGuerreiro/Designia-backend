import logging

from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

from marketplace.models import Product

User = get_user_model()
logger = logging.getLogger(__name__)


class UserClick(models.Model):
    """
    Track user interactions with products including views, favorites, and cart additions.
    This model consolidates all user activity to efficiently track product engagement.
    """

    ACTION_CHOICES = [
        ("view", "Product View"),
        ("listing_view", "Product Listing View"),
        ("detail_view", "Product Detail View"),
        ("click", "Product Click"),
        ("favorite", "Add to Favorites"),
        ("unfavorite", "Remove from Favorites"),
        ("cart_add", "Add to Cart"),
        ("cart_remove", "Remove from Cart"),
        ("purchase", "Product Purchase"),
        ("search_view", "Search Result View"),
        ("category_view", "Category Listing View"),
        ("share", "Product Share"),
        ("review", "Product Review"),
        ("contact_seller", "Contact Seller"),
        ("image_view", "Product Image View"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="activity_clicks", null=True, blank=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="activity_clicks")
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)

    # Session tracking for anonymous users
    session_key = models.CharField(max_length=40, null=True, blank=True)

    # Request metadata
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    referer = models.URLField(blank=True, null=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["product", "action", "created_at"]),
            models.Index(fields=["user", "action", "created_at"]),
            models.Index(fields=["session_key", "action", "created_at"]),
            models.Index(fields=["created_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        user_identifier = self.user.username if self.user else f"Session: {self.session_key}"
        return f"{user_identifier} - {self.action} - {self.product.name}"

    @classmethod
    def track_activity(cls, product, action, user=None, session_key=None, request=None):
        """
        Create a new activity record and update product metrics.

        Args:
            product: Product instance
            action: Action type ('view', 'favorite', 'unfavorite', 'cart_add', 'cart_remove', 'click')
            user: User instance (optional for anonymous users)
            session_key: Session key for anonymous users
            request: HttpRequest object for metadata
        """
        from datetime import timedelta

        # Prevent duplicate view tracking within a very short time window (e.g., 1 second)
        # to avoid double-counting from React StrictMode, double-clicks, or immediate page refreshes
        # but still allow legitimate repeat visits
        if action in ["view", "detail_view", "listing_view", "category_view", "search_view"]:
            time_threshold = timezone.now() - timedelta(seconds=1)  # Short window

            # Check for very recent similar activity by the same user/session
            existing_activity = cls.objects.filter(
                product=product,
                action=action,  # Only check for the exact same action type
                created_at__gte=time_threshold,
            )

            if user:
                existing_activity = existing_activity.filter(user=user)
            elif session_key:
                existing_activity = existing_activity.filter(session_key=session_key)
            else:
                # For requests without user or session, still allow tracking
                # Don't prevent anonymous users from being tracked
                pass

            if existing_activity.exists():
                # Return the most recent existing activity instead of creating a duplicate
                logger.debug(
                    f"Duplicate view prevented (within 1s): {product.name} by {user or session_key or 'anonymous'}"
                )
                return existing_activity.first()

        # Extract request metadata
        ip_address = None
        user_agent = ""
        referer = None

        if request:
            # Get IP address
            x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
            if x_forwarded_for:
                ip_address = x_forwarded_for.split(",")[0]
            else:
                ip_address = request.META.get("REMOTE_ADDR")

            user_agent = request.META.get("HTTP_USER_AGENT", "")
            referer = request.META.get("HTTP_REFERER")

        # Create activity record
        activity = cls.objects.create(
            user=user,
            product=product,
            action=action,
            session_key=session_key,
            ip_address=ip_address,
            user_agent=user_agent,
            referer=referer,
        )

        # Update product metrics
        activity.update_product_metrics()

        return activity

    def update_product_metrics(self):
        """Update ProductMetrics based on this activity"""
        # Get or create product metrics
        from decimal import Decimal

        from marketplace.models import ProductMetrics

        metrics, created = ProductMetrics.objects.get_or_create(
            product=self.product,
            defaults={
                "total_views": 0,
                "total_clicks": 0,
                "total_favorites": 0,
                "total_cart_additions": 0,
                "total_sales": 0,
                "total_revenue": Decimal("0.00"),
            },
        )

        # Update counters based on action
        if self.action in ["view", "detail_view", "listing_view", "search_view", "category_view", "image_view"]:
            metrics.total_views += 1
        elif self.action == "click":
            metrics.total_clicks += 1
        elif self.action == "favorite":
            metrics.total_favorites += 1
        elif self.action == "unfavorite":
            # Decrease favorites count but don't go below 0
            metrics.total_favorites = max(0, metrics.total_favorites - 1)
        elif self.action == "cart_add":
            # Cart additions count as both cart additions AND clicks (since adding to cart is a user interaction/click)
            metrics.total_cart_additions += 1
            metrics.total_clicks += 1
        elif self.action == "cart_remove":
            # We don't decrease cart additions as they represent total attempts
            pass
        elif self.action == "purchase":
            # Purchase metrics are handled separately in the tracking utils
            pass

        # Save the updated metrics
        metrics.save()


class ActivitySummary(models.Model):
    """
    Daily/weekly/monthly activity summaries for analytics and reporting.
    This model provides aggregated data for better performance on analytics queries.
    """

    PERIOD_CHOICES = [
        ("daily", "Daily"),
        ("weekly", "Weekly"),
        ("monthly", "Monthly"),
    ]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="activity_summaries")
    period_type = models.CharField(max_length=10, choices=PERIOD_CHOICES)
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()

    # Activity counts
    total_views = models.PositiveIntegerField(default=0)
    total_clicks = models.PositiveIntegerField(default=0)
    total_favorites = models.PositiveIntegerField(default=0)
    total_unfavorites = models.PositiveIntegerField(default=0)
    total_cart_additions = models.PositiveIntegerField(default=0)
    total_cart_removals = models.PositiveIntegerField(default=0)

    # Unique users/sessions
    unique_users = models.PositiveIntegerField(default=0)
    unique_sessions = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["product", "period_type", "period_start"]
        indexes = [
            models.Index(fields=["product", "period_type", "period_start"]),
            models.Index(fields=["period_start", "period_end"]),
        ]
        ordering = ["-period_start"]

    def __str__(self):
        return f"{self.product.name} - {self.period_type} - {self.period_start.date()}"

    @classmethod
    def generate_daily_summary(cls, product, date):
        """Generate daily activity summary for a product"""
        from datetime import datetime, time

        # Define the day period
        start_time = datetime.combine(date, time.min)
        end_time = datetime.combine(date, time.max)

        # Get activities for this day
        activities = UserClick.objects.filter(product=product, created_at__range=[start_time, end_time])

        # Calculate aggregates
        summary_data = {
            "total_views": activities.filter(action="view").count(),
            # Total clicks includes both 'click' actions and 'cart_add' actions (since cart addition is a click interaction)
            "total_clicks": activities.filter(action__in=["click", "cart_add"]).count(),
            "total_favorites": activities.filter(action="favorite").count(),
            "total_unfavorites": activities.filter(action="unfavorite").count(),
            "total_cart_additions": activities.filter(action="cart_add").count(),
            "total_cart_removals": activities.filter(action="cart_remove").count(),
            "unique_users": activities.filter(user__isnull=False).values("user").distinct().count(),
            "unique_sessions": activities.filter(session_key__isnull=False).values("session_key").distinct().count(),
        }

        # Create or update summary
        summary, created = cls.objects.update_or_create(
            product=product,
            period_type="daily",
            period_start=start_time,
            defaults={"period_end": end_time, **summary_data},
        )

        return summary
