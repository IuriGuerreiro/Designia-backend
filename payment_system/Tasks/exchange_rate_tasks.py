"""
Exchange Rate Celery Tasks

Handles daily exchange rate updates.
"""
import logging
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, queue='marketplace_tasks')
def update_exchange_rates_task(self):
    """
    Celery task to update exchange rates daily.
    
    Returns:
        dict: Update result
    """
    try:
        from ..services.exchange_rate_service import ExchangeRateService
        
        logger.info("Starting daily exchange rate update task")
        
        result = ExchangeRateService.update_exchange_rates(
            force_update=True,
            cleanup_old=True,
            source='celery_daily_task'
        )
        
        if result['success']:
            if result.get('skipped'):
                logger.info(f"Exchange rate update completed: {result['message']}")
            else:
                logger.info(f"Exchange rate update completed: {result['created_count']} rates updated")
        else:
            logger.error(f"Exchange rate update failed: {result['error']}")
            # Retry with exponential backoff
            try:
                raise self.retry(countdown=60 * (2 ** self.request.retries))
            except self.MaxRetriesExceededError:
                result['error'] = f"Max retries exceeded: {result['error']}"
        
        return result
        
    except Exception as e:
        logger.error(f"Error in exchange rate update task: {e}")
        # Retry with exponential backoff
        try:
            raise self.retry(countdown=60 * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            return {
                'success': False,
                'created_count': 0,
                'error': f'Max retries exceeded: {str(e)}'
            }
