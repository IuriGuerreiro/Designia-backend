"""
Celery Configuration for Designia Backend

This module configures Celery for handling asynchronous tasks and scheduled jobs.
Includes payment timeout handling, exchange rate updates, and other background tasks.
"""

import os

from celery import Celery


# Set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "designiaBackend.settings")

# Create Celery app
app = Celery("designiaBackend")

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Explicitly import our tasks to ensure they're registered
app.autodiscover_tasks(["payment_system.Tasks"])

# Celery Beat configuration for periodic tasks
app.conf.beat_schedule = {
    # Daily exchange rate update at midnight UTC
    "update-exchange-rates-daily": {
        "task": "payment_system.Tasks.exchange_rate_tasks.update_exchange_rates_task",
        "schedule": 60.0 * 60.0 * 24.0,  # 24 hours
        "options": {"expires": 30.0 * 60.0, "queue": "marketplace_tasks"},  # Expire after 30 minutes if not executed
    },
    # Check for payment timeouts every hour
    "check-payment-timeouts": {
        "task": "payment_system.Tasks.payment_tasks.check_payment_timeouts_task",
        "schedule": 60.0 * 60.0,  # Every hour
        "options": {"expires": 15.0 * 60.0, "queue": "payment_tasks"},  # Expire after 15 minutes
    },
}

# Celery configuration settings
app.conf.update(
    # Task routing - organize tasks by type
    task_routes={
        "payment_system.Tasks.payment_tasks.*": {"queue": "payment_tasks"},
        "payment_system.Tasks.exchange_rate_tasks.*": {"queue": "marketplace_tasks"},
        "marketplace.tasks.*": {"queue": "marketplace_tasks"},
    },
    # Task execution settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Task result settings
    result_backend="redis://localhost:6379/1",
    result_expires=60 * 60 * 24,  # Results expire after 24 hours
    # Worker settings
    worker_pool_restarts=True,
    worker_max_tasks_per_child=1000,
    worker_disable_rate_limits=False,
    # Task execution settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
    # Beat scheduler settings
    beat_scheduler="django_celery_beat.schedulers:DatabaseScheduler",
)
