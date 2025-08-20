"""
Celery-based Scheduler Service

Replaces APScheduler with Celery for reliable background task scheduling.
Provides management interface for periodic tasks using Django-Celery-Beat.
"""
import logging
from typing import Optional, Dict, List
from django.utils import timezone
from django_celery_beat.models import PeriodicTask, CrontabSchedule, IntervalSchedule

logger = logging.getLogger(__name__)


class CelerySchedulerService:
    """
    Service for managing Celery-based scheduled tasks.
    Provides a clean interface for task scheduling and monitoring.
    """
    
    @classmethod
    def setup_default_tasks(cls) -> Dict[str, bool]:
        """
        Set up essential periodic tasks for the payment system.
        
        Returns:
            dict: Results of task setup operations
        """
        results = {}
        
        try:
            # Daily exchange rate update at midnight UTC
            results['exchange_rates'] = cls.schedule_daily_exchange_rates()
            
            # Hourly payment timeout checks
            results['payment_timeouts'] = cls.schedule_payment_timeout_checks()
            
            logger.info("Essential Celery tasks setup completed")
            return results
            
        except Exception as e:
            logger.error(f"Error setting up essential tasks: {e}")
            return {
                'error': str(e),
                'exchange_rates': False,
                'payment_timeouts': False
            }
    
    @classmethod
    def schedule_daily_exchange_rates(cls, hour: int = 0, minute: int = 0) -> bool:
        """
        Schedule daily exchange rate updates.
        
        Args:
            hour (int): Hour for daily update (0-23, default: 0 for midnight)
            minute (int): Minute for daily update (0-59, default: 0)
            
        Returns:
            bool: True if scheduled successfully
        """
        try:
            # Create or update crontab schedule
            schedule, created = CrontabSchedule.objects.get_or_create(
                minute=minute,
                hour=hour,
                day_of_week='*',
                day_of_month='*',
                month_of_year='*',
                timezone='UTC'
            )
            
            # Create or update periodic task
            task, task_created = PeriodicTask.objects.update_or_create(
                name='Daily Exchange Rate Update',
                defaults={
                    'task': 'payment_system.Tasks.exchange_rate_tasks.update_exchange_rates_task',
                    'crontab': schedule,
                    'enabled': True,
                    'description': 'Updates exchange rates daily from external API',
                    'expires': timezone.now() + timezone.timedelta(hours=2),  # Allow 2 hours for completion
                }
            )
            
            action = "created" if task_created else "updated"
            logger.info(f"Daily exchange rate task {action}: runs at {hour:02d}:{minute:02d} UTC")
            
            return True
            
        except Exception as e:
            logger.error(f"Error scheduling daily exchange rate updates: {e}")
            return False
    
    @classmethod
    def schedule_payment_timeout_checks(cls, interval_hours: int = 1) -> bool:
        """
        Schedule periodic payment timeout checks.
        
        Args:
            interval_hours (int): Hours between checks (default: 1)
            
        Returns:
            bool: True if scheduled successfully
        """
        try:
            # Create or update interval schedule
            schedule, created = IntervalSchedule.objects.get_or_create(
                every=interval_hours,
                period=IntervalSchedule.HOURS,
            )
            
            # Create or update periodic task
            task, task_created = PeriodicTask.objects.update_or_create(
                name='Payment Timeout Check',
                defaults={
                    'task': 'payment_system.Tasks.payment_tasks.check_payment_timeouts_task',
                    'interval': schedule,
                    'enabled': True,
                    'description': 'Checks for orders that have exceeded payment timeout and cancels them',
                    'expires': timezone.now() + timezone.timedelta(minutes=30),  # Allow 30 minutes for completion
                }
            )
            
            action = "created" if task_created else "updated"
            logger.info(f"Payment timeout check task {action}: runs every {interval_hours} hour(s)")
            
            return True
            
        except Exception as e:
            logger.error(f"Error scheduling payment timeout checks: {e}")
            return False
    
    
    @classmethod
    def get_task_status(cls) -> Dict:
        """
        Get status of all scheduled tasks.
        
        Returns:
            dict: Status of all scheduled tasks
        """
        try:
            tasks = PeriodicTask.objects.filter(
                task__startswith='payment_system.Tasks.'
            )
            
            task_status = {
                'total_tasks': tasks.count(),
                'enabled_tasks': tasks.filter(enabled=True).count(),
                'disabled_tasks': tasks.filter(enabled=False).count(),
                'tasks': []
            }
            
            for task in tasks:
                task_info = {
                    'name': task.name,
                    'task': task.task,
                    'enabled': task.enabled,
                    'last_run_at': task.last_run_at.isoformat() if task.last_run_at else None,
                    'total_run_count': task.total_run_count,
                    'description': task.description or '',
                }
                
                # Add schedule information
                if task.crontab:
                    task_info['schedule_type'] = 'crontab'
                    task_info['schedule'] = f"{task.crontab.minute} {task.crontab.hour} {task.crontab.day_of_week} {task.crontab.day_of_month} {task.crontab.month_of_year}"
                elif task.interval:
                    task_info['schedule_type'] = 'interval'
                    task_info['schedule'] = f"Every {task.interval.every} {task.interval.period}"
                else:
                    task_info['schedule_type'] = 'unknown'
                    task_info['schedule'] = 'No schedule found'
                
                task_status['tasks'].append(task_info)
            
            return task_status
            
        except Exception as e:
            logger.error(f"Error getting task status: {e}")
            return {
                'error': str(e),
                'total_tasks': 0,
                'enabled_tasks': 0,
                'disabled_tasks': 0,
                'tasks': []
            }
    
    @classmethod
    def enable_task(cls, task_name: str) -> bool:
        """
        Enable a specific scheduled task.
        
        Args:
            task_name (str): Name of the task to enable
            
        Returns:
            bool: True if enabled successfully
        """
        try:
            task = PeriodicTask.objects.get(name=task_name)
            task.enabled = True
            task.save()
            
            logger.info(f"Enabled task: {task_name}")
            return True
            
        except PeriodicTask.DoesNotExist:
            logger.error(f"Task not found: {task_name}")
            return False
        except Exception as e:
            logger.error(f"Error enabling task {task_name}: {e}")
            return False
    
    @classmethod
    def disable_task(cls, task_name: str) -> bool:
        """
        Disable a specific scheduled task.
        
        Args:
            task_name (str): Name of the task to disable
            
        Returns:
            bool: True if disabled successfully
        """
        try:
            task = PeriodicTask.objects.get(name=task_name)
            task.enabled = False
            task.save()
            
            logger.info(f"Disabled task: {task_name}")
            return True
            
        except PeriodicTask.DoesNotExist:
            logger.error(f"Task not found: {task_name}")
            return False
        except Exception as e:
            logger.error(f"Error disabling task {task_name}: {e}")
            return False
    
    @classmethod
    def trigger_manual_update(cls, task_name: str = 'exchange_rates') -> Dict:
        """
        Trigger a manual execution of a scheduled task.
        
        Args:
            task_name (str): Type of task to trigger ('exchange_rates', 'payment_timeouts', 'webhook_cleanup')
            
        Returns:
            dict: Task execution result
        """
        try:
            from ..Tasks import (
                update_exchange_rates_task, 
                check_payment_timeouts_task
            )
            
            task_map = {
                'exchange_rates': update_exchange_rates_task,
                'payment_timeouts': check_payment_timeouts_task
            }
            
            if task_name not in task_map:
                return {
                    'success': False,
                    'error': f'Unknown task name: {task_name}. Available: {list(task_map.keys())}'
                }
            
            logger.info(f"Triggering manual execution of {task_name} task")
            
            # Execute task asynchronously
            task_result = task_map[task_name].delay()
            
            return {
                'success': True,
                'message': f'Task {task_name} triggered manually',
                'task_id': task_result.id,
                'task_name': task_name
            }
            
        except Exception as e:
            error_msg = f"Manual trigger failed for {task_name}: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'task_name': task_name
            }
    
    @classmethod
    def cleanup_old_tasks(cls, days: int = 30) -> Dict:
        """
        Clean up old task execution records.
        
        Args:
            days (int): Number of days to keep records (default: 30)
            
        Returns:
            dict: Cleanup result
        """
        try:
            from django_celery_beat.models import PeriodicTaskChanged
            from django.db import connection
            
            # Clean up old PeriodicTaskChanged records
            cutoff_date = timezone.now() - timezone.timedelta(days=days)
            deleted_count = PeriodicTaskChanged.objects.filter(
                last_update__lt=cutoff_date
            ).delete()[0]
            
            logger.info(f"Cleaned up {deleted_count} old task change records")
            
            # Clean up Celery result backend if using database
            try:
                with connection.cursor() as cursor:
                    cursor.execute("""
                        DELETE FROM celery_taskmeta 
                        WHERE date_done < %s
                    """, [cutoff_date])
                    result_count = cursor.rowcount
                    
                logger.info(f"Cleaned up {result_count} old Celery task results")
            except Exception as e:
                logger.warning(f"Could not clean Celery results (may not be using database backend): {e}")
                result_count = 0
            
            return {
                'success': True,
                'deleted_task_changes': deleted_count,
                'deleted_results': result_count,
                'cutoff_date': cutoff_date.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error cleaning up old tasks: {e}")
            return {
                'success': False,
                'error': str(e)
            }


def get_celery_installation_guide() -> str:
    """
    Get installation and setup guide for Celery.
    
    Returns:
        str: Installation and usage instructions
    """
    return """
    Celery + Redis Setup Guide:
    
    1. Install dependencies:
       pip install celery[redis] django-celery-beat redis
    
    2. Start Redis server:
       redis-server
    
    3. Start Celery worker:
       celery -A designiaBackend worker -l info -Q payment_tasks,marketplace_tasks
    
    4. Start Celery Beat scheduler:
       celery -A designiaBackend beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
    
    5. Monitor tasks:
       celery -A designiaBackend flower  # Optional web interface
    
    Task Organization:
    - payment_system.Tasks.payment_tasks: Payment timeout handling
    - payment_system.Tasks.exchange_rate_tasks: Currency exchange rate updates
    
    Features:
    - Reliable task scheduling with database persistence
    - Automatic retry with exponential backoff
    - Task routing to different queues for better resource management
    - Web-based monitoring and management
    - Better error handling and logging
    """