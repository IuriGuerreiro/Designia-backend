from django.apps import AppConfig


class MarketplaceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "marketplace"

    def ready(self):
        # Register event listeners
        try:
            from marketplace.infra.events.listeners import register_marketplace_listeners

            register_marketplace_listeners()
        except Exception:
            # Don't crash app startup if redis is not available
            # Use standard print as logger might not be fully configured yet during startup in some contexts
            pass
