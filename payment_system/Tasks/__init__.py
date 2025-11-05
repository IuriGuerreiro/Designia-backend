"""
Payment System Tasks Package

Simplified Celery task definitions for the payment system.
Provides essential task management for payment timeouts and exchange rates.
"""

from .exchange_rate_tasks import update_exchange_rates_task

# Import essential tasks to ensure they are registered with Celery
from .payment_tasks import cancel_expired_order, check_payment_timeouts_task

# Export essential tasks for easy importing
__all__ = [
    # Payment tasks
    "cancel_expired_order",
    "check_payment_timeouts_task",
    # Exchange rate tasks
    "update_exchange_rates_task",
]
