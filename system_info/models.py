from django.db import models


class AppVersion(models.Model):
    """
    Model to track mandatory app versions for different platforms.
    Used to enforce mandatory updates for mobile apps.
    """

    PLATFORM_CHOICES = [
        ("android", "Android"),
        ("ios", "iOS"),
    ]

    platform = models.CharField(
        max_length=10, choices=PLATFORM_CHOICES, unique=True, help_text="Platform (Android or iOS)"
    )

    mandatory_version = models.CharField(max_length=20, help_text="Minimum required version (e.g., '1.3.0')")

    latest_version = models.CharField(max_length=20, help_text="Latest available version (e.g., '1.4.0')")

    update_message = models.TextField(blank=True, help_text="Message to show users when update is required")

    download_url = models.URLField(blank=True, help_text="URL to download the latest version")

    is_active = models.BooleanField(default=True, help_text="Whether this version check is active")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "App Version"
        verbose_name_plural = "App Versions"
        ordering = ["platform"]

    def __str__(self):
        return f"{self.platform} - Mandatory: {self.mandatory_version}, Latest: {self.latest_version}"
