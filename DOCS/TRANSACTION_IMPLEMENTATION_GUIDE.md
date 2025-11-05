# MySQL Transaction Implementation Guide

## Overview

This guide covers the comprehensive MySQL transaction implementation across the Designia backend, featuring global transaction utilities with isolation level control and extensive application in payment system and marketplace operations.

## Architecture

### Global Transaction Utilities (`utils/transaction_utils.py`)

The transaction system provides several layers of abstraction:

1. **Low-level utilities** - Direct isolation level control
2. **Decorators** - Automatic transaction wrapping
3. **Context managers** - Fine-grained transaction control
4. **Convenience functions** - Domain-specific transaction patterns

### Key Components

#### Isolation Levels
- `READ UNCOMMITTED` - Lowest isolation, allows dirty reads
- `READ COMMITTED` - Prevents dirty reads
- `REPEATABLE READ` - Prevents dirty and non-repeatable reads (MySQL default)
- `SERIALIZABLE` - Highest isolation, prevents phantom reads

#### Transaction Decorators
- `@financial_transaction` - For financial operations (SERIALIZABLE)
- `@product_transaction` - For product operations (REPEATABLE READ)
- `@transactional(isolation_level)` - Custom isolation level
- `@serializable_transaction` - Maximum isolation wrapper

#### Context Managers
- `atomic_with_isolation(level)` - Transaction with custom isolation
- `rollback_safe_operation(name)` - Named operation with rollback safety

## Implementation Details

### Payment System Integration

All critical payment operations now use `@financial_transaction` decorator which provides:
- **SERIALIZABLE** isolation level for maximum data consistency
- **Automatic deadlock retry** with exponential backoff
- **Performance logging** for monitoring transaction times
- **Comprehensive error handling** with rollback safety

#### Updated Functions:
```python
@financial_transaction
def stripe_webhook(request):
    # Stripe webhook processing with maximum isolation

@financial_transaction
def handle_successful_payment(session):
    # Payment confirmation with ACID compliance

@financial_transaction
def cancel_order(request, order_id):
    # Order cancellation with refund processing

# Manual seller payout creation endpoint has been retired and now returns a 410 Gone response.
# The transfer operations endpoint continues to run under the transaction safety wrapper.

@financial_transaction
def transfer_payment_to_seller(request):
    # Transfer operations with atomicity
```

#### Transaction Contexts:
All `transaction.atomic()` calls replaced with `atomic_with_isolation('SERIALIZABLE')`:
```python
# Old pattern
with transaction.atomic():
    order.status = 'cancelled'
    order.save()

# New pattern
with atomic_with_isolation('SERIALIZABLE'):
    order.status = 'cancelled'
    order.save()
```

### Marketplace Integration

Product operations use `@product_transaction` decorator which provides:
- **REPEATABLE READ** isolation for consistency without excessive locking
- **Automatic metrics initialization** for new products
- **Stock validation** within transaction boundaries
- **Review and image creation** with atomicity

#### Updated Functions:
```python
@product_transaction
def create(self, request, *args, **kwargs):
    # Product creation with metrics initialization

@product_transaction
def perform_create(self, serializer):
    # Atomic product creation with metrics

@product_transaction
def update_item(self, request):
    # Cart item updates with stock validation
```

#### Enhanced Product Creation:
```python
def perform_create(self, serializer):
    with atomic_with_isolation('REPEATABLE READ'):
        # Create the product
        product = serializer.save(seller=user)

        # Ensure ProductMetrics exists atomically
        MetricsHelper.ensure_metrics_for_product(product)

        return product
```

### Error Handling and Recovery

#### Deadlock Detection and Retry
```python
@retry_on_deadlock(max_retries=3, delay=0.1, backoff=2.0)
def critical_operation():
    # Automatically retries on MySQL deadlock (error 1213)
    pass
```

#### Rollback Safety
```python
with rollback_safe_operation("Payment Processing"):
    # Operations that might need rollback
    create_payment_record()
    update_order_status()
    # Automatic rollback on any exception
```

#### Custom Exception Handling
```python
try:
    with atomic_with_isolation('SERIALIZABLE'):
        # Critical financial operation
        pass
except TransactionError as e:
    # Handle transaction-specific errors
    logger.error(f"Transaction failed: {e}")
except DeadlockError as e:
    # Handle deadlock-specific errors
    logger.warning(f"Deadlock detected: {e}")
```

## Usage Patterns

### Financial Operations
For any operation involving money, payments, or financial state:
```python
@financial_transaction
def process_payment(payment_data):
    # Use SERIALIZABLE isolation
    # Automatic retry on deadlock
    # Performance monitoring included
    pass
```

### Product Operations
For product creation, updates, or inventory management:
```python
@product_transaction
def manage_inventory(product_id, changes):
    # Use REPEATABLE READ isolation
    # Good balance of consistency and performance
    pass
```

### Custom Isolation
For specific requirements:
```python
@transactional(isolation_level='READ COMMITTED', retry_deadlocks=True)
def custom_operation():
    # Custom isolation level
    # Optional deadlock retry
    pass
```

### Context Manager Usage
For fine-grained control:
```python
with atomic_with_isolation('SERIALIZABLE'):
    # Critical section with maximum isolation
    update_financial_records()

with rollback_safe_operation("Complex Operation"):
    # Named operation with automatic rollback
    perform_multiple_updates()
```

## Performance Considerations

### Transaction Monitoring
```python
@log_transaction_performance
@financial_transaction
def monitored_operation():
    # Automatic performance logging
    pass
```

### Isolation Level Impact
- **SERIALIZABLE**: Highest consistency, potential for more deadlocks
- **REPEATABLE READ**: Good balance, suitable for most operations
- **READ COMMITTED**: Lower consistency, better performance
- **READ UNCOMMITTED**: Lowest consistency, highest performance

### Best Practices
1. **Minimize transaction scope** - Keep transactions as short as possible
2. **Use appropriate isolation levels** - Don't over-isolate
3. **Handle deadlocks gracefully** - Use retry decorators
4. **Monitor performance** - Use logging decorators
5. **Test rollback scenarios** - Ensure proper error handling

## Configuration

### Database Settings
Ensure your MySQL configuration supports the isolation levels:
```sql
-- Check current isolation level
SELECT @@transaction_isolation;

-- Set session isolation level
SET SESSION TRANSACTION ISOLATION LEVEL SERIALIZABLE;
```

### Django Settings
Configure transaction behavior in `settings.py`:
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'OPTIONS': {
            'isolation_level': 'REPEATABLE READ',
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    }
}
```

## Testing

### Running Transaction Tests
```bash
# Run the comprehensive test suite
python test_transaction_rollback.py

# Test specific scenarios
python manage.py shell
>>> from utils.transaction_utils import *
>>> with atomic_with_isolation('SERIALIZABLE'):
...     print("Testing SERIALIZABLE isolation")
```

### Test Coverage
The test suite covers:
- ✅ Successful transaction commit
- ✅ Transaction rollback on error
- ✅ Isolation level testing
- ✅ Deadlock handling and retry
- ✅ Performance monitoring
- ✅ Nested transaction support
- ✅ Transaction statistics

## Monitoring and Debugging

### Transaction Statistics
```python
from utils.transaction_utils import TransactionMonitor

# Get current transaction stats
stats = TransactionMonitor.get_transaction_stats()
print(f"Commits: {stats.get('Com_commit', 0)}")
print(f"Rollbacks: {stats.get('Com_rollback', 0)}")
print(f"Deadlocks: {stats.get('Innodb_deadlocks', 0)}")
```

### Deadlock Information
```python
# Log deadlock details for debugging
TransactionMonitor.log_deadlock_info()
```

### Current Isolation Level
```python
# Check current isolation level
level = get_current_isolation_level()
print(f"Current isolation: {level}")
```

## Migration Guide

### From Old Code
```python
# Old pattern
with transaction.atomic():
    model.save()

# New pattern
with atomic_with_isolation('REPEATABLE READ'):
    model.save()
```

### Adding Decorators
```python
# Old function
def payment_function():
    with transaction.atomic():
        # payment logic
        pass

# New function
@financial_transaction
def payment_function():
    # payment logic (transaction handled by decorator)
    pass
```

## Security Considerations

### Financial Operations
- Always use `SERIALIZABLE` isolation for money-related operations
- Implement proper input validation before transaction boundaries
- Use rollback-safe operations for multi-step financial processes
- Log all financial transactions for audit trails

### Data Integrity
- Use appropriate isolation levels for data consistency requirements
- Implement deadlock retry for critical operations
- Validate permissions within transaction boundaries
- Handle edge cases with proper error recovery

## Troubleshooting

### Common Issues

#### Deadlocks
```
Solution: Use @retry_on_deadlock decorator or lower isolation level
```

#### Long-Running Transactions
```
Solution: Minimize transaction scope, use connection pooling
```

#### Performance Issues
```
Solution: Monitor with @log_transaction_performance, optimize queries
```

#### Isolation Level Errors
```
Solution: Verify MySQL supports requested isolation level
```

## Future Enhancements

1. **Connection Pooling Optimization** - Improve connection management
2. **Distributed Transaction Support** - Cross-database transactions
3. **Automatic Performance Tuning** - Dynamic isolation level adjustment
4. **Advanced Monitoring** - Real-time transaction metrics dashboard
5. **ML-Based Deadlock Prediction** - Predictive deadlock avoidance

## Resources

- [MySQL Transaction Isolation](https://dev.mysql.com/doc/refman/8.0/en/innodb-transaction-isolation-levels.html)
- [Django Transaction Documentation](https://docs.djangoproject.com/en/stable/topics/db/transactions/)
- [ACID Properties](https://en.wikipedia.org/wiki/ACID)
- [Deadlock Detection and Resolution](https://dev.mysql.com/doc/refman/8.0/en/innodb-deadlocks.html)
