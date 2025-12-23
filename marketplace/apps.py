from django.apps import AppConfig


class MarketplaceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "marketplace"

    def ready(self):
        # Register event listeners
        try:
            from marketplace.infra.events.listeners import register_marketplace_listeners

            register_marketplace_listeners()
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Failed to register marketplace listeners: {e}")
