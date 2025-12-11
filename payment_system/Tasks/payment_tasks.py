"""
Payment System Celery Tasks

Handles payment-related asynchronous tasks including:
- Payment timeout handling (3-day grace period)
- Order cancellation after payment timeout with stock restoration
- Payment transaction cancellation management
- Delayed payment confirmation processing
"""

import logging
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone


# Removed unused transaction_utils import

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, queue="payment_tasks")
def cancel_expired_order(self, order_id):  # noqa: C901
    """
    Cancel an order that has exceeded the 3-day payment timeout.
    Restores stock to products and cancels payment transactions.

    Args:
        order_id (str): The UUID of the order to cancel

    Returns:
        dict: Cancellation result including restored items and cancelled transactions
    """
    try:
        from marketplace.models import Order

        logger.info(f"Cancelling expired order {order_id}")

        with transaction.atomic():
            # Get the order with lock
            try:
                order = Order.objects.select_for_update().get(id=order_id)
            except Order.DoesNotExist:
                logger.warning(f"Order {order_id} not found for cancellation")
                return {"success": False, "error": "Order not found", "order_id": order_id}

            # Double-check order is still pending and expired
            three_days_ago = timezone.now() - timedelta(days=3)

            if order.status != "pending_payment":
                logger.info(f"Order {order_id} status is {order.status}, not pending_payment. Skipping cancellation.")
                return {
                    "success": True,
                    "message": "Order no longer pending payment",
                    "order_id": order_id,
                    "order_status": order.status,
                }

            if order.created_at > three_days_ago:
                logger.info(f"Order {order_id} is not yet expired. Created: {order.created_at}")
                return {
                    "success": True,
                    "message": "Order not yet expired",
                    "order_id": order_id,
                    "days_remaining": 3 - (timezone.now() - order.created_at).days,
                }

            # Cancel the order
            order.status = "cancelled"
            order.payment_status = "failed"
            order.cancellation_reason = "Payment timeout - Order cancelled after 3-day grace period"
            order.cancelled_at = timezone.now()
            order.admin_notes = (
                f"{order.admin_notes}\nOrder automatically cancelled due to payment timeout (3 days)"
                if order.admin_notes
                else "Order automatically cancelled due to payment timeout (3 days)"
            )

            order.save(
                update_fields=[
                    "status",
                    "payment_status",
                    "cancellation_reason",
                    "cancelled_at",
                    "admin_notes",
                    "updated_at",
                ]
            )

            # Restore stock to products before canceling
            from ..models import PaymentTransaction

            restored_items = []

            for order_item in order.items.all():
                try:
                    # Get the product and restore stock
                    product = order_item.product
                    if product and product.is_active:
                        # Restore the stock quantity that was reserved for this order
                        original_stock = product.stock_quantity
                        product.stock_quantity += order_item.quantity
                        product.save(update_fields=["stock_quantity", "updated_at"])

                        restored_items.append(
                            {
                                "product_id": str(product.id),
                                "product_name": order_item.product_name,
                                "quantity_restored": order_item.quantity,
                                "previous_stock": original_stock,
                                "new_stock": product.stock_quantity,
                            }
                        )

                        logger.info(
                            f"Restored {order_item.quantity} units of {order_item.product_name} to stock. Stock: {original_stock} -> {product.stock_quantity}"
                        )
                    else:
                        logger.warning(
                            f"Product {order_item.product_name} not found or inactive - cannot restore stock"
                        )

                except Exception as e:
                    logger.error(f"Error restoring stock for {order_item.product_name}: {e}")
                    # Continue with other items even if one fails

            # Cancel related payment transactions
            cancelled_transactions = 0
            cancelled_payment_transactions = []

            # Cancel any non-terminal payment transactions for this order
            transactions = (
                PaymentTransaction.objects.filter(order=order)
                .exclude(status__in=["completed", "released", "refunded", "failed", "cancelled"])
                .select_for_update()
            )

            # Also, find and cancel any related transfers for the order
            try:
                from ..models import Transfer

                transfers_to_cancel = Transfer.objects.filter(order=order).exclude(
                    status__in=["completed", "failed", "cancelled"]
                )
                for transfer in transfers_to_cancel:
                    transfer.status = "cancelled"
                    transfer.save(update_fields=["status", "updated_at"])
                    logger.info(f"Cancelled Transfer {transfer.id} for order {order.id}")
            except ImportError:
                # If Transfer model doesn't exist, skip this step
                logger.info("Transfer model not found, skipping transfer cancellation.")
                pass

            for payment_txn in transactions:
                try:
                    # Use the cancel_payment method if available, otherwise update manually
                    if hasattr(payment_txn, "cancel_payment"):
                        payment_txn.cancel_payment(
                            cancellation_reason="Payment timeout - Order cancelled after 3-day grace period",
                            notes="Order automatically cancelled due to payment timeout",
                        )
                    else:
                        # Fallback manual update
                        payment_txn.status = "cancelled"
                        payment_txn.payment_failure_code = "cancelled"
                        payment_txn.payment_failure_reason = (
                            "Payment timeout - Order cancelled after 3-day grace period"
                        )
                        payment_txn.save(
                            update_fields=["status", "payment_failure_code", "payment_failure_reason", "updated_at"]
                        )

                    cancelled_payment_transactions.append(
                        {
                            "transaction_id": str(payment_txn.id),
                            "seller": payment_txn.seller.username if payment_txn.seller else "Unknown",
                            "gross_amount": str(payment_txn.gross_amount),
                            "status": payment_txn.status,
                        }
                    )
                    cancelled_transactions += 1

                    logger.info(f"Cancelled PaymentTransaction {payment_txn.id} for seller {payment_txn.seller}")

                except Exception as e:
                    logger.error(f"Error cancelling PaymentTransaction {payment_txn.id}: {e}")
                    # Continue with other transactions even if one fails

            logger.info(
                f"Successfully cancelled expired order {order_id}, restored {len(restored_items)} products, and cancelled {cancelled_transactions} transactions"
            )

            # TODO: Send cancellation email to buyer
            # send_order_cancellation_email(order.buyer, order, 'payment_timeout')

            return {
                "success": True,
                "message": "Order cancelled due to payment timeout",
                "order_id": order_id,
                "cancelled_transactions": cancelled_transactions,
                "restored_items": restored_items,
                "cancelled_payment_transactions": cancelled_payment_transactions,
                "cancelled_at": order.cancelled_at.isoformat(),
            }

    except Exception as e:
        logger.error(f"Error cancelling expired order {order_id}: {e}")
        return {"success": False, "error": str(e), "order_id": order_id}


@shared_task(bind=True, max_retries=3, queue="payment_tasks")
def check_payment_timeouts_task(self):
    """
    Periodic task to check for orders that need payment timeout processing.
    Runs every hour to find orders that are approaching or past the 3-day limit.

    Returns:
        dict: Task execution result
    """
    try:
        from marketplace.models import Order

        logger.info("Starting payment timeout check task")

        # Find orders that are pending payment for more than 3 days
        three_days_ago = timezone.now() - timedelta(days=3)

        # Get expired orders (no locking needed for read-only query)
        expired_orders = Order.objects.filter(status="pending_payment", created_at__lte=three_days_ago)

        results = {
            "success": True,
            "total_expired": expired_orders.count(),
            "cancelled_orders": [],
            "total_stock_restored": 0,
            "total_transactions_cancelled": 0,
            "errors": [],
        }

        logger.info(f"Found {results['total_expired']} orders to cancel due to payment timeout")

        for order in expired_orders:
            try:
                cancel_result = cancel_expired_order(str(order.id))
                if cancel_result["success"]:
                    restored_items = cancel_result.get("restored_items", [])
                    cancelled_payment_transactions = cancel_result.get("cancelled_payment_transactions", [])

                    results["cancelled_orders"].append(
                        {
                            "order_id": str(order.id),
                            "cancelled_at": cancel_result.get("cancelled_at"),
                            "cancelled_transactions": cancel_result.get("cancelled_transactions", 0),
                            "restored_items_count": len(restored_items),
                            "cancelled_payment_transactions_count": len(cancelled_payment_transactions),
                        }
                    )

                    results["total_stock_restored"] += len(restored_items)
                    results["total_transactions_cancelled"] += len(cancelled_payment_transactions)
                else:
                    results["errors"].append(
                        {"order_id": str(order.id), "error": cancel_result.get("error", "Unknown error")}
                    )
            except Exception as e:
                logger.error(f"Error processing expired order {order.id}: {e}")
                results["errors"].append({"order_id": str(order.id), "error": str(e)})

        logger.info(
            f"Payment timeout check completed. Cancelled: {len(results['cancelled_orders'])}, Stock restored: {results['total_stock_restored']}, Transactions cancelled: {results['total_transactions_cancelled']}, Errors: {len(results['errors'])}"
        )

        return results

    except Exception as e:
        logger.error(f"Error in payment timeout check task: {e}")
        # Retry with exponential backoff
        try:
            raise self.retry(countdown=60 * (2**self.request.retries))
        except self.MaxRetriesExceededError:
            return {
                "success": False,
                "error": f"Max retries exceeded: {str(e)}",
                "total_expired": 0,
                "cancelled_orders": [],
                "errors": [{"error": str(e)}],
            }
