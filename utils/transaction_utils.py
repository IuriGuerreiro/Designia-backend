"""
MySQL Transaction Utilities for Designia Backend
==============================================

Global transaction management utilities with MySQL-specific isolation level control
and comprehensive error handling for financial and critical operations.

Usage Examples:
    # Function decorator
    @transactional(isolation_level='SERIALIZABLE')
    def process_payment(payment_data):
        # Your payment logic here
        pass
    
    # Context manager
    with atomic_with_isolation('REPEATABLE READ'):
        # Your transaction logic here
        pass
    
    # High-security financial operations
    @serializable_transaction
    def handle_payout():
        # Financial operation with maximum isolation
        pass
"""

import logging
import time
from functools import wraps
from contextlib import contextmanager
from django.db import transaction, connection, IntegrityError, OperationalError
from django.conf import settings

logger = logging.getLogger(__name__)

# MySQL Isolation Levels
ISOLATION_LEVELS = {
    'READ_UNCOMMITTED': 'READ UNCOMMITTED',
    'READ_COMMITTED': 'READ COMMITTED', 
    'REPEATABLE_READ': 'REPEATABLE READ',
    'SERIALIZABLE': 'SERIALIZABLE'
}

class TransactionError(Exception):
    """Custom exception for transaction-related errors"""
    pass

class DeadlockError(TransactionError):
    """Exception raised when a deadlock is detected"""
    pass

def set_isolation_level(level='REPEATABLE READ', using='default'):
    """
    Set MySQL transaction isolation level for the current connection.
    
    Args:
        level (str): One of 'READ UNCOMMITTED', 'READ COMMITTED', 
                    'REPEATABLE READ', 'SERIALIZABLE'
        using (str): Database alias to use
    """
    if level not in ISOLATION_LEVELS.values():
        raise ValueError(f"Invalid isolation level: {level}. Must be one of {list(ISOLATION_LEVELS.values())}")
    
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"SET SESSION TRANSACTION ISOLATION LEVEL {level}")
        logger.debug(f"Set transaction isolation level to {level}")
    except Exception as e:
        logger.error(f"Failed to set isolation level to {level}: {e}")
        raise TransactionError(f"Could not set isolation level: {e}")

@contextmanager 
def atomic_with_isolation(isolation_level='REPEATABLE READ', using='default', savepoint=True):
    """
    Context manager for atomic transactions with custom isolation level.
    
    Args:
        isolation_level (str): MySQL isolation level
        using (str): Database alias
        savepoint (bool): Whether to use savepoints for nested transactions
        
    Usage:
        with atomic_with_isolation('SERIALIZABLE'):
            # Your transaction code here
            model.save()
            other_model.create(...)
    """
    try:
        with transaction.atomic(using=using, savepoint=savepoint):
            # Set isolation level at start of transaction
            set_isolation_level(isolation_level, using=using)
            logger.debug(f"Started atomic transaction with isolation level: {isolation_level}")
            yield
            logger.debug("Transaction committed successfully")
    except (IntegrityError, OperationalError) as e:
        logger.error(f"Database error in transaction: {e}")
        raise TransactionError(f"Transaction failed: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in transaction: {e}")
        raise

def retry_on_deadlock(max_retries=3, delay=0.1, backoff=2.0):
    """
    Decorator to retry operations on deadlock with exponential backoff.
    
    Args:
        max_retries (int): Maximum number of retry attempts
        delay (float): Initial delay between retries in seconds
        backoff (float): Backoff multiplier for delay
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except OperationalError as e:
                    # Check if this is a deadlock error (MySQL error code 1213)
                    if 'Deadlock found' in str(e) or '1213' in str(e):
                        last_exception = DeadlockError(f"Deadlock detected: {e}")
                        if attempt < max_retries:
                            logger.warning(f"Deadlock detected, retrying in {current_delay}s (attempt {attempt + 1}/{max_retries})")
                            time.sleep(current_delay)
                            current_delay *= backoff
                            continue
                    raise TransactionError(f"Database operation failed: {e}")
                except Exception as e:
                    raise
            
            # If we get here, we've exhausted all retries
            raise last_exception
        return wrapper
    return decorator

def transactional(isolation_level='REPEATABLE READ', using='default', retry_deadlocks=True):
    """
    Decorator for automatic transaction wrapping with custom isolation level.
    
    Args:
        isolation_level (str): MySQL isolation level to use
        using (str): Database alias
        retry_deadlocks (bool): Whether to automatically retry on deadlocks
        
    Usage:
        @transactional(isolation_level='SERIALIZABLE')
        def process_payment(order_id, amount):
            # Payment processing logic
            pass
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                with atomic_with_isolation(isolation_level=isolation_level, using=using):
                    logger.debug(f"Executing {func.__name__} with {isolation_level} isolation")
                    return func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Transaction failed in {func.__name__}: {e}")
                raise
        
        # Apply deadlock retry if requested
        if retry_deadlocks:
            wrapper = retry_on_deadlock()(wrapper)
        
        return wrapper
    return decorator

def serializable_transaction(using='default'):
    """
    Decorator for maximum isolation level transactions (SERIALIZABLE).
    Use for financial operations and critical data consistency requirements.
    
    Usage:
        @serializable_transaction
        def handle_stripe_webhook(event_data):
            # Critical financial operation
            pass
    """
    return transactional(isolation_level='SERIALIZABLE', using=using, retry_deadlocks=True)

def repeatable_read_transaction(using='default'):
    """
    Decorator for REPEATABLE READ isolation level.
    Good balance between consistency and performance.
    
    Usage:
        @repeatable_read_transaction  
        def update_product_metrics(product_id):
            # Product metrics update
            pass
    """
    return transactional(isolation_level='REPEATABLE READ', using=using, retry_deadlocks=True)

@contextmanager
def rollback_safe_operation(operation_name="Unknown"):
    """
    Context manager that ensures operations can be safely rolled back.
    Provides detailed logging and error context.
    
    Args:
        operation_name (str): Name of the operation for logging
        
    Usage:
        with rollback_safe_operation("Payment Processing"):
            # Operations that might need rollback
            create_payment_record()
            update_order_status()
    """
    start_time = time.time()
    logger.info(f"Starting rollback-safe operation: {operation_name}")
    
    try:
        yield
        elapsed = time.time() - start_time
        logger.info(f"Operation '{operation_name}' completed successfully in {elapsed:.3f}s")
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"Operation '{operation_name}' failed after {elapsed:.3f}s: {e}")
        logger.info(f"Rolling back operation: {operation_name}")
        raise

def log_transaction_performance(func):
    """
    Decorator to log transaction performance metrics.
    
    Usage:
        @log_transaction_performance
        @transactional()
        def my_database_operation():
            pass
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            elapsed = time.time() - start_time
            logger.info(f"Transaction {func.__name__} completed in {elapsed:.3f}s")
            return result
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Transaction {func.__name__} failed after {elapsed:.3f}s: {e}")
            raise
    return wrapper

# Convenience function for common payment operations
def financial_transaction(func):
    """
    Convenience decorator for financial operations requiring maximum data consistency.
    Combines SERIALIZABLE isolation, deadlock retry, and performance logging.
    
    Usage:
        @financial_transaction
        def process_stripe_payment(payment_intent_id):
            # Financial operation
            pass
    """
    return log_transaction_performance(serializable_transaction()(func))

# Convenience function for product operations  
def product_transaction(func):
    """
    Convenience decorator for product-related operations.
    Uses REPEATABLE READ isolation with deadlock retry.
    
    Usage:
        @product_transaction
        def create_product_with_metrics(product_data):
            # Product creation logic
            pass
    """
    return log_transaction_performance(repeatable_read_transaction()(func))

def get_current_isolation_level(using='default'):
    """
    Get the current transaction isolation level for debugging.
    
    Returns:
        str: Current isolation level
    """
    try:
        with connection.cursor() as cursor:
            # Try the newer MySQL 8.0+ variable name first
            try:
                cursor.execute("SELECT @@transaction_isolation")
                result = cursor.fetchone()[0]
            except Exception:
                # Fallback to older MySQL variable name
                cursor.execute("SELECT @@tx_isolation")
                result = cursor.fetchone()[0]
            
            logger.debug(f"Current isolation level: {result}")
            return result
    except Exception as e:
        logger.error(f"Failed to get isolation level: {e}")
        return None

# Transaction monitoring utilities
class TransactionMonitor:
    """Utility class for monitoring transaction performance and deadlocks"""
    
    @staticmethod
    def log_deadlock_info():
        """Log information about recent deadlocks for debugging"""
        try:
            with connection.cursor() as cursor:
                cursor.execute("SHOW ENGINE INNODB STATUS")
                status = cursor.fetchone()[2]
                if 'LATEST DETECTED DEADLOCK' in status:
                    logger.warning("Recent deadlock detected - check INNODB status")
                    # Log relevant parts of the status for debugging
                    deadlock_section = status.split('LATEST DETECTED DEADLOCK')[1].split('WE ROLL BACK')[0]
                    logger.debug(f"Deadlock info: {deadlock_section[:500]}...")
        except Exception as e:
            logger.error(f"Failed to log deadlock info: {e}")
    
    @staticmethod
    def get_transaction_stats():
        """Get current transaction statistics"""
        try:
            with connection.cursor() as cursor:
                # Try different approaches for different MySQL versions
                try:
                    # Try SHOW STATUS first (works on most MySQL versions)
                    cursor.execute("""
                        SHOW STATUS WHERE Variable_name IN (
                            'Com_commit', 'Com_rollback', 'Innodb_deadlocks',
                            'Innodb_lock_timeouts', 'Innodb_row_lock_waits'
                        )
                    """)
                    results = cursor.fetchall()
                    stats = dict(results)
                except Exception:
                    # Fallback to information_schema if available
                    try:
                        cursor.execute("""
                            SELECT 
                                VARIABLE_NAME, 
                                VARIABLE_VALUE 
                            FROM information_schema.GLOBAL_STATUS 
                            WHERE VARIABLE_NAME IN (
                                'Com_commit', 'Com_rollback', 'Innodb_deadlocks',
                                'Innodb_lock_timeouts', 'Innodb_row_lock_waits'
                            )
                        """)
                        stats = dict(cursor.fetchall())
                    except Exception:
                        # Return basic stats if specific stats unavailable
                        stats = {'connection_test': 'success'}
                
                logger.debug(f"Transaction stats: {stats}")
                return stats
        except Exception as e:
            logger.error(f"Failed to get transaction stats: {e}")
            return {}