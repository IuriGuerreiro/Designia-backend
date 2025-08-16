"""
Scheduler Service

Handles scheduled tasks for the payment system, particularly daily exchange rate updates.
Uses APScheduler for reliable background task scheduling.
"""
import logging
import threading
from typing import Optional
from django.utils import timezone
from django.conf import settings

logger = logging.getLogger(__name__)

# Global scheduler instance
_scheduler = None
_scheduler_lock = threading.Lock()


class SchedulerService:
    """
    Service for managing scheduled tasks, particularly exchange rate updates.
    """
    
    @classmethod
    def start_daily_updates(cls, update_hour: int = 0, update_minute: int = 0) -> bool:
        """
        Start daily exchange rate updates at specified time.
        
        Args:
            update_hour (int): Hour for daily update (0-23, default: 0 for midnight)
            update_minute (int): Minute for daily update (0-59, default: 0)
            
        Returns:
            bool: True if scheduler started successfully, False otherwise
        """
        try:
            # Try to use APScheduler, fall back to simple threading if not available
            if cls._start_apscheduler(update_hour, update_minute):
                return True
            else:
                return cls._start_simple_scheduler(update_hour, update_minute)
                
        except Exception as e:
            logger.error(f"[ERROR] Failed to start daily scheduler: {e}")
            return False
    
    @classmethod
    def _start_apscheduler(cls, update_hour: int, update_minute: int) -> bool:
        """
        Start scheduler using APScheduler (preferred method).
        
        Args:
            update_hour (int): Hour for daily update
            update_minute (int): Minute for daily update
            
        Returns:
            bool: True if APScheduler started successfully, False if not available
        """
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.cron import CronTrigger
            from apscheduler.executors.pool import ThreadPoolExecutor
            
            global _scheduler, _scheduler_lock
            
            with _scheduler_lock:
                if _scheduler is not None:
                    logger.info("[SKIP] Scheduler already running, skipping start")
                    return True
                
                # Configure scheduler
                executors = {
                    'default': ThreadPoolExecutor(max_workers=2)
                }
                
                job_defaults = {
                    'coalesce': True,  # Combine multiple pending executions
                    'max_instances': 1,  # Only one instance of job at a time
                    'misfire_grace_time': 300  # 5 minutes grace period
                }
                
                _scheduler = BackgroundScheduler(
                    executors=executors,
                    job_defaults=job_defaults,
                    timezone=timezone.get_current_timezone()
                )
                
                # Add daily exchange rate update job
                _scheduler.add_job(
                    func=cls._daily_update_job,
                    trigger=CronTrigger(hour=update_hour, minute=update_minute),
                    id='daily_exchange_rate_update',
                    name='Daily Exchange Rate Update',
                    replace_existing=True
                )
                
                # Start the scheduler
                _scheduler.start()
                
                logger.info(f"[SUCCESS] APScheduler started successfully - daily updates at {update_hour:02d}:{update_minute:02d}")
                return True
                
        except ImportError:
            logger.warning("[WARNING] APScheduler not available, falling back to simple scheduler")
            return False
        except Exception as e:
            logger.error(f"[ERROR] Failed to start APScheduler: {e}")
            return False
    
    @classmethod
    def _start_simple_scheduler(cls, update_hour: int, update_minute: int) -> bool:
        """
        Start simple thread-based scheduler (fallback method).
        
        Args:
            update_hour (int): Hour for daily update
            update_minute (int): Minute for daily update
            
        Returns:
            bool: True if simple scheduler started successfully
        """
        try:
            import time
            from datetime import datetime, timedelta
            
            def simple_scheduler():
                """Simple scheduler that runs daily at specified time."""
                logger.info(f"🕐 Simple scheduler started - daily updates at {update_hour:02d}:{update_minute:02d}")
                
                while True:
                    try:
                        # Calculate next update time
                        now = timezone.now()
                        next_update = now.replace(
                            hour=update_hour, 
                            minute=update_minute, 
                            second=0, 
                            microsecond=0
                        )
                        
                        # If time has passed today, schedule for tomorrow
                        if next_update <= now:
                            next_update += timedelta(days=1)
                        
                        # Calculate sleep time
                        sleep_seconds = (next_update - now).total_seconds()
                        
                        logger.info(f"[SCHEDULE] Next exchange rate update scheduled for {next_update}")
                        logger.info(f"[WAIT] Sleeping for {sleep_seconds:.0f} seconds ({sleep_seconds/3600:.1f} hours)")
                        
                        # Sleep until next update
                        time.sleep(sleep_seconds)
                        
                        # Run the update
                        logger.info("[SCHEDULED] Running scheduled exchange rate update...")
                        cls._daily_update_job()
                        
                    except Exception as e:
                        logger.error(f"[ERROR] Error in simple scheduler: {e}")
                        # Sleep for 1 hour before retrying
                        time.sleep(3600)
            
            # Start scheduler in daemon thread
            scheduler_thread = threading.Thread(
                target=simple_scheduler,
                name='ExchangeRateScheduler',
                daemon=True
            )
            scheduler_thread.start()
            
            logger.info("[SUCCESS] Simple scheduler started successfully")
            return True
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to start simple scheduler: {e}")
            return False
    
    @classmethod
    def _daily_update_job(cls):
        """
        The actual job that runs daily to update exchange rates.
        """
        try:
            from .exchange_rate_service import ExchangeRateService
            
            logger.info("[DAILY] Starting daily exchange rate update job...")
            
            # Update exchange rates with cleanup
            result = ExchangeRateService.update_exchange_rates(
                force_update=True,  # Always update during scheduled runs
                cleanup_old=True,   # Clean up old data
                source='daily_scheduled'
            )
            
            if result['success']:
                if result.get('skipped'):
                    logger.info(f"[SUCCESS] Daily update completed: {result['message']}")
                else:
                    logger.info(f"[SUCCESS] Daily update completed: {result['created_count']} rates updated")
            else:
                logger.error(f"[ERROR] Daily update failed: {result['error']}")
                
        except Exception as e:
            logger.error(f"[ERROR] Error in daily update job: {e}")
    
    @classmethod
    def stop_scheduler(cls) -> bool:
        """
        Stop the scheduler gracefully.
        
        Returns:
            bool: True if stopped successfully
        """
        try:
            global _scheduler, _scheduler_lock
            
            with _scheduler_lock:
                if _scheduler is not None:
                    _scheduler.shutdown(wait=False)
                    _scheduler = None
                    logger.info("[STOP] Scheduler stopped successfully")
                    return True
                else:
                    logger.info("[INFO] Scheduler was not running")
                    return True
                    
        except Exception as e:
            logger.error(f"[ERROR] Error stopping scheduler: {e}")
            return False
    
    @classmethod
    def get_scheduler_status(cls) -> dict:
        """
        Get current scheduler status and next scheduled update.
        
        Returns:
            dict: Scheduler status information
        """
        try:
            global _scheduler
            
            if _scheduler is None:
                return {
                    'running': False,
                    'scheduler_type': 'none',
                    'next_run': None,
                    'status': 'stopped'
                }
            
            try:
                # Try to get APScheduler info
                jobs = _scheduler.get_jobs()
                if jobs:
                    next_run = jobs[0].next_run_time
                    return {
                        'running': True,
                        'scheduler_type': 'apscheduler',
                        'next_run': next_run.isoformat() if next_run else None,
                        'jobs_count': len(jobs),
                        'status': 'running'
                    }
                else:
                    return {
                        'running': True,
                        'scheduler_type': 'apscheduler',
                        'next_run': None,
                        'jobs_count': 0,
                        'status': 'running_no_jobs'
                    }
            except:
                # Probably simple scheduler
                return {
                    'running': True,
                    'scheduler_type': 'simple',
                    'next_run': None,
                    'status': 'running'
                }
                
        except Exception as e:
            logger.error(f"[ERROR] Error getting scheduler status: {e}")
            return {
                'running': False,
                'scheduler_type': 'unknown',
                'next_run': None,
                'status': 'error',
                'error': str(e)
            }
    
    @classmethod
    def trigger_manual_update(cls) -> dict:
        """
        Trigger a manual exchange rate update outside of schedule.
        
        Returns:
            dict: Update result
        """
        try:
            from .exchange_rate_service import ExchangeRateService
            
            logger.info("[MANUAL] Manual exchange rate update triggered")
            
            result = ExchangeRateService.update_exchange_rates(
                force_update=True,
                cleanup_old=True,
                source='manual_trigger'
            )
            
            return result
            
        except Exception as e:
            error_msg = f"Manual update failed: {str(e)}"
            logger.error(f"[ERROR] {error_msg}")
            return {
                'success': False,
                'created_count': 0,
                'error': error_msg
            }


def get_apscheduler_installation_guide() -> str:
    """
    Get installation guide for APScheduler.
    
    Returns:
        str: Installation instructions
    """
    return """
    To enable advanced scheduling features, install APScheduler:
    
    pip install APScheduler
    
    APScheduler provides:
    - More reliable scheduling
    - Better error handling
    - Job persistence options
    - Advanced scheduling options
    
    Without APScheduler, the system will use a simple thread-based scheduler.
    """