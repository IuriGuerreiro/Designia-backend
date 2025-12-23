import logging
import threading

from django.apps import AppConfig


logger = logging.getLogger(__name__)


class PaymentSystemConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "payment_system"
    verbose_name = "Payment System"

    def ready(self):
        """Initialize payment system when Django starts"""
        # Import security configurations to ensure they're loaded
        # Only run in the main process, not in reloaders or migrations
        import os

        # Register event listeners (Must run in all processes)
        try:
            from payment_system.infra.events.listeners import register_payment_listeners

            register_payment_listeners()
        except Exception as e:
            logger.error(f"Failed to register payment listeners: {e}")

        if os.environ.get("RUN_MAIN") != "true":
            return

        # Don't run during migrations
        if any(arg in ["migrate", "makemigrations", "showmigrations"] for arg in __import__("sys").argv):
            return

        logger.info("[STARTUP] Payment System starting up...")

        # Start the automatic exchange rate update system
        self._start_exchange_rate_updates()

        # Start the daily scheduler
        self._start_daily_scheduler()

        logger.info("[SUCCESS] Payment System startup complete")

    def _start_exchange_rate_updates(self):
        """
        Update exchange rates on server startup in a background thread.
        """

        def update_on_startup():
            try:
                from .domain.services.exchange_rate_service import ExchangeRateService

                logger.info("[UPDATE] Starting server startup exchange rate update...")

                # Update exchange rates on startup
                result = ExchangeRateService.update_exchange_rates(
                    force_update=False,  # Respect freshness check
                    cleanup_old=True,  # Clean up old data
                    source="startup",
                )

                if result["success"]:
                    logger.info(
                        f"[SUCCESS] Startup exchange rate update completed: {result['created_count']} rates updated"
                    )
                else:
                    logger.warning(f"[WARNING] Startup exchange rate update failed: {result['error']}")

            except Exception as e:
                logger.error(f"[ERROR] Error during startup exchange rate update: {e}")

        # Run in background thread to not block server startup
        startup_thread = threading.Thread(target=update_on_startup, daemon=True)
        startup_thread.start()

    def _start_daily_scheduler(self):
        """
        Start the daily scheduler for midnight exchange rate updates.
        """

        def start_scheduler():
            try:
                from .domain.services.scheduler_service import SchedulerService

                logger.info("[SCHEDULER] Starting daily exchange rate scheduler...")

                # Start the daily scheduler
                SchedulerService.start_daily_updates()

                logger.info("[SUCCESS] Daily scheduler started successfully")

            except Exception as e:
                logger.error(f"[ERROR] Error starting daily scheduler: {e}")

        # Run scheduler in background thread
        scheduler_thread = threading.Thread(target=start_scheduler, daemon=True)
        scheduler_thread.start()
