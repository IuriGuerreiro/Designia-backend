from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone


User = get_user_model()


class SellerApplication(models.Model):
    """Seller application model for approval workflow"""

    STATUS_CHOICES = [
        ("pending", "Pending Review"),
        ("under_review", "Under Review"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("revision_requested", "Revision Requested"),
    ]

    SELLER_TYPE_CHOICES = [
        ("manufacturer", "Manufacturer"),
        ("designer", "Furniture Designer"),
        ("restorer", "Furniture Restorer/Fixer"),
        ("retailer", "Retailer/Curator"),
        ("artisan", "Artisan/Craftsman"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="seller_application")

    # Application fields from BecomeSellerForm
    business_name = models.CharField(max_length=200)
    seller_type = models.CharField(max_length=20, choices=SELLER_TYPE_CHOICES)
    motivation = models.TextField(help_text="Why they want to sell on Designia")
    portfolio_url = models.URLField(help_text="Portfolio or website link")
    social_media_url = models.URLField(blank=True, help_text="Social media link (optional)")

    # Application status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    admin_notes = models.TextField(blank=True, help_text="Admin notes for review")
    rejection_reason = models.TextField(blank=True, help_text="Reason for rejection")

    # Timestamps and approval tracking
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_applications",
        help_text="Admin who approved this application",
    )
    rejected_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rejected_applications",
        help_text="Admin who rejected this application",
    )

    class Meta:
        app_label = "authentication"
        verbose_name = "Seller Application"
        verbose_name_plural = "Seller Applications"
        ordering = ["-submitted_at"]

    def approve_application(self, admin_user):
        """Approve the seller application"""
        self.status = "approved"
        self.reviewed_at = timezone.now()
        self.approved_by = admin_user
        self.save()

        # Upgrade user to seller role
        self.user.role = "seller"
        self.user.save()

        # Update profile
        profile = self.user.profile
        profile.is_verified_seller = True
        profile.seller_type = self.seller_type
        profile.save()

    def reject_application(self, admin_user, reason):
        """Reject the seller application"""
        self.status = "rejected"
        self.reviewed_at = timezone.now()
        self.rejected_by = admin_user
        self.rejection_reason = reason
        self.save()

    def request_revision(self, admin_user, notes):
        """Request revision of the application"""
        self.status = "revision_requested"
        self.reviewed_at = timezone.now()
        self.rejected_by = admin_user  # Track who requested revision
        self.admin_notes = notes
        self.save()

    def __str__(self):
        return f"Seller Application by {self.user.email}"


class SellerApplicationImage(models.Model):
    """Images for seller applications (workshop/inventory/business photos)"""

    IMAGE_TYPE_CHOICES = [
        ("workshop", "Workshop Photo"),
        ("inventory", "Inventory Photo"),
        ("product_sample", "Product Sample"),
        ("business_setup", "Business Setup"),
        ("tools_equipment", "Tools & Equipment"),
        ("other", "Other"),
    ]

    application = models.ForeignKey(SellerApplication, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="seller_applications/")
    image_type = models.CharField(
        max_length=20, choices=IMAGE_TYPE_CHOICES, default="workshop", help_text="Type of business image"
    )
    description = models.CharField(max_length=200, blank=True, help_text="Description of what this image shows")
    order = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "authentication"
        ordering = ["order", "uploaded_at"]

    def __str__(self):
        return f"{self.get_image_type_display()} for {self.application.user.email}'s application"
