from django.contrib.auth import get_user_model
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from .catalog import Product


User = get_user_model()


class ProductReview(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    reviewer = models.ForeignKey(User, on_delete=models.SET_NULL, related_name="reviews", null=True, blank=True)
    # Stores reviewer display name for GDPR compliance (when reviewer is deleted/anonymized)
    reviewer_name = models.CharField(max_length=150, blank=True, default="")
    rating = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    title = models.CharField(max_length=200, blank=True)
    comment = models.TextField(blank=True)
    is_verified_purchase = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    helpful_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Changed from unique_together to allow multiple reviews with null reviewer
        constraints = [
            models.UniqueConstraint(
                fields=["product", "reviewer"],
                condition=models.Q(reviewer__isnull=False),
                name="unique_product_reviewer",
            )
        ]
        ordering = ["-created_at"]
        app_label = "marketplace"

    def get_reviewer_display_name(self):
        """Return the display name for the reviewer."""
        if self.reviewer:
            return self.reviewer.username
        return self.reviewer_name or "Deleted User"

    def __str__(self):
        return f"Review by {self.get_reviewer_display_name()} for {self.product.name}"


class ProductReviewHelpful(models.Model):
    review = models.ForeignKey(ProductReview, on_delete=models.CASCADE, related_name="helpful_votes")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="helpful_reviews")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["review", "user"]
        app_label = "marketplace"

    def __str__(self):
        return f"{self.user.username} found review {self.review.id} helpful"


class ProductFavorite(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="favorites")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="favorited_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["user", "product"]
        app_label = "marketplace"
        indexes = [
            models.Index(fields=["user", "product"]),  # For favorite checks
            models.Index(fields=["product"]),  # For product's favorite list
            models.Index(fields=["user"]),  # For user's favorites
            models.Index(fields=["created_at"]),  # For ordering
        ]

    def __str__(self):
        return f"{self.user.username} favorited {self.product.name}"


class ProductMetrics(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name="metrics")
    total_views = models.PositiveIntegerField(default=0)
    total_clicks = models.PositiveIntegerField(default=0)
    total_favorites = models.PositiveIntegerField(default=0)
    total_cart_additions = models.PositiveIntegerField(default=0)
    total_sales = models.PositiveIntegerField(default=0)
    total_revenue = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "marketplace"

    @property
    def view_to_click_rate(self):
        if self.total_views > 0:
            return self.total_clicks / self.total_views
        return 0.0

    @property
    def click_to_cart_rate(self):
        if self.total_clicks > 0:
            return self.total_cart_additions / self.total_clicks
        return 0.0

    @property
    def cart_to_purchase_rate(self):
        if self.total_cart_additions > 0:
            return self.total_sales / self.total_cart_additions
        return 0.0

    def __str__(self):
        return f"Metrics for {self.product.name}"
