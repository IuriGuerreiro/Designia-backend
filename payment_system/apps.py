from django.apps import AppConfig


class PaymentSystemConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'payment_system'
    verbose_name = 'Payment System'

    def ready(self):
        """Initialize payment system when Django starts"""
        # Import security configurations to ensure they're loaded
        from . import security
        
        # Initialize any background tasks or signal handlers
        # This ensures all security measures are loaded at startup
        pass
