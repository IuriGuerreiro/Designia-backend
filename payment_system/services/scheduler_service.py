"""
Scheduler Service - DEPRECATED

This service has been migrated to use Celery for better reliability and scalability.
Use CelerySchedulerService instead.

Legacy compatibility wrapper that delegates to Celery-based implementation.
"""

import logging
import warnings
from typing import Dict

from .celery_scheduler_service import CelerySchedulerService


logger = logging.getLogger(__name__)

# Deprecation warning
warnings.warn("SchedulerService is deprecated. Use CelerySchedulerService instead.", DeprecationWarning, stacklevel=2)


class SchedulerService:
    """
    DEPRECATED: Legacy compatibility wrapper for CelerySchedulerService.
    Use CelerySchedulerService directly for new implementations.
    """

    @classmethod
    def start_daily_updates(cls, update_hour: int = 0, update_minute: int = 0) -> bool:
        """
        DEPRECATED: Use CelerySchedulerService.schedule_daily_exchange_rates() instead.
        """
        logger.warning("SchedulerService.start_daily_updates() is deprecated. Use CelerySchedulerService instead.")

        try:
            return CelerySchedulerService.schedule_daily_exchange_rates(update_hour, update_minute)
        except Exception as e:
            logger.error(f"Failed to start Celery-based daily scheduler: {e}")
            return False

    @classmethod
    def stop_scheduler(cls) -> bool:
        """
        DEPRECATED: Use CelerySchedulerService.disable_task() instead.
        """
        logger.warning("SchedulerService.stop_scheduler() is deprecated. Use CelerySchedulerService instead.")

        try:
            return CelerySchedulerService.disable_task("Daily Exchange Rate Update")
        except Exception as e:
            logger.error(f"Failed to stop scheduler: {e}")
            return False

    @classmethod
    def get_scheduler_status(cls) -> Dict:
        """
        DEPRECATED: Use CelerySchedulerService.get_task_status() instead.
        """
        logger.warning("SchedulerService.get_scheduler_status() is deprecated. Use CelerySchedulerService instead.")

        try:
            celery_status = CelerySchedulerService.get_task_status()

            # Convert to legacy format for compatibility
            if "error" in celery_status:
                return {
                    "running": False,
                    "scheduler_type": "celery",
                    "next_run": None,
                    "status": "error",
                    "error": celery_status["error"],
                }

            return {
                "running": celery_status["enabled_tasks"] > 0,
                "scheduler_type": "celery",
                "next_run": None,  # Celery doesn't provide next run time easily
                "total_tasks": celery_status["total_tasks"],
                "enabled_tasks": celery_status["enabled_tasks"],
                "status": "running" if celery_status["enabled_tasks"] > 0 else "stopped",
            }

        except Exception as e:
            logger.error(f"Failed to get scheduler status: {e}")
            return {"running": False, "scheduler_type": "celery", "next_run": None, "status": "error", "error": str(e)}

    @classmethod
    def trigger_manual_update(cls) -> Dict:
        """
        DEPRECATED: Use CelerySchedulerService.trigger_manual_update() instead.
        """
        logger.warning("SchedulerService.trigger_manual_update() is deprecated. Use CelerySchedulerService instead.")

        try:
            return CelerySchedulerService.trigger_manual_update("exchange_rates")
        except Exception as e:
            error_msg = f"Manual update failed: {str(e)}"
            logger.error(error_msg)
            return {"success": False, "created_count": 0, "error": error_msg}


def get_apscheduler_installation_guide() -> str:
    """
    Get updated installation guide for Celery (replaces APScheduler).
    """
    return (
        CelerySchedulerService.get_celery_installation_guide()
        if hasattr(CelerySchedulerService, "get_celery_installation_guide")
        else """
    APScheduler has been replaced with Celery for better reliability.

    To use the new Celery-based scheduler:

    1. Install dependencies:
       pip install celery[redis] django-celery-beat redis

    2. Use CelerySchedulerService instead of SchedulerService:
       from payment_system.services.celery_scheduler_service import CelerySchedulerService

       # Setup default tasks
       CelerySchedulerService.setup_default_tasks()

       # Get status
       status = CelerySchedulerService.get_task_status()

       # Trigger manual update
       result = CelerySchedulerService.trigger_manual_update('exchange_rates')

    3. Start Celery worker and beat:
       celery -A designiaBackend worker -l info
       celery -A designiaBackend beat -l info
    """
    )
