import uuid

from django.db import models

from authentication.domain.models.user import CustomUser  # Assuming CustomUser is the correct User model
from marketplace.ordering.domain.models.order import Order


class ReturnRequest(models.Model):
    RETURN_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("processed", "Processed"),
        ("cancelled", "Cancelled"),
    ]

    RETURN_REASON_CHOICES = [
        ("defective", "Defective Product"),
        ("wrong_item", "Wrong Item Shipped"),
        ("size_too_small", "Size Too Small"),
        ("size_too_large", "Size Too Large"),
        ("change_of_mind", "Change of Mind"),
        ("other", "Other"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="return_requests")
    requested_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="return_requests")

    reason = models.CharField(max_length=50, choices=RETURN_REASON_CHOICES, default="other")
    comment = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=RETURN_STATUS_CHOICES, default="pending")

    # Store image URLs, assuming they are uploaded to S3 or similar and we store the URLs
    # For simplicity, we can use a JSONField or a simple TextField for multiple URLs
    # In a real app, this might be a separate Image model related to ReturnRequest
    proof_image_urls = models.JSONField(blank=True, null=True, help_text="List of URLs for proof images")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Fields for admin approval/processing
    approved_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_returns"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Return Request"
        verbose_name_plural = "Return Requests"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Return Request {self.id} for Order {self.order.id} - Status: {self.status}"
