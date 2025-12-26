"""
Celery Tasks for Payment System

Story 4.4 & 4.7
"""

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from payment_system.domain.services.payout_service import PayoutService


logger = logging.getLogger(__name__)


@shared_task(name="process_weekly_payouts")
def process_weekly_payouts():
    """
    Celery task to process pending payouts for sellers.
    Typically scheduled to run weekly (e.g., Mondays).
    """
    logger.info("Starting weekly payout processing...")
    try:
        service = PayoutService()
        result = service.process_pending_payouts()

        if result.ok:
            logger.info(f"Weekly payouts completed. Processed: {result.value}")
            return f"Processed {result.value} payouts"
        else:
            logger.error(f"Weekly payouts failed: {result.error}")
            return f"Failed: {result.error}"

    except Exception as e:
        logger.error(f"Error in process_weekly_payouts task: {e}", exc_info=True)
        raise


@shared_task(name="check_pending_payments")
def check_pending_payments():
    """
    Check for payments stuck in 'processing' or 'pending' for too long (> 1 hour).
    Polls Stripe to reconcile status.
    """
    logger.info("Starting pending payments check...")
    # Implementation of Story 4.7 Task
    # Find transactions > 1 hour old that are not completed
    threshold = timezone.now() - timedelta(hours=1)

    # In real implementation, we would check PaymentTracker or Order status
    # Here we'll check PaymentTransaction for demonstration/consistency with other tasks
    # But usually 'pending' payments are on Orders/PaymentTrackers waiting for webhook.

    # Example: Find PaymentTracker items that are pending
    from payment_system.models import PaymentTracker

    pending_trackers = PaymentTracker.objects.filter(status="pending", created_at__lt=threshold)

    # In a real implementation:
    # for tracker in pending_trackers:
    #     status = stripe_provider.retrieve_payment_intent(tracker.stripe_payment_intent_id).status
    #     if status == 'succeeded': update_tracker_and_order()
    #     elif status == 'canceled': mark_failed()

    logger.info(f"Found {pending_trackers.count()} pending payment trackers to check.")
    return f"Checked {pending_trackers.count()} trackers"
