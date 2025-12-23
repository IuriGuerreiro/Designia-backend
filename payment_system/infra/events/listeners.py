import logging

from django.contrib.auth import get_user_model

from infrastructure.events import get_event_bus
from marketplace.models import Order
from payment_system.infra.payment_provider.stripe_provider import StripePaymentProvider
from payment_system.models import PaymentTracker, PaymentTransaction


logger = logging.getLogger(__name__)
User = get_user_model()
payment_provider = StripePaymentProvider()


def handle_order_cancelled(event_data):
    """
    Handle order.cancelled event.
    Initiates a refund if the order was paid.
    """
    try:
        payload = event_data.get("payload", {})
        order_id = payload.get("order_id")
        user_id = payload.get("user_id")
        reason = payload.get("reason", "Order cancelled")
        payment_status = payload.get("payment_status")

        logger.info(f"[Payment Listener] Handling cancellation for order {order_id} (status: {payment_status})")

        if payment_status != "paid":
            logger.info(f"Order {order_id} is not paid, skipping refund.")
            return

        # Retrieve order and user for context
        try:
            order = Order.objects.get(id=order_id)
            user = User.objects.get(id=user_id)
        except (Order.DoesNotExist, User.DoesNotExist) as e:
            logger.error(f"Failed to retrieve entities for refund: {e}")
            return

        # Find successful payment tracker
        payment_tracker = PaymentTracker.objects.filter(
            order=order, transaction_type="payment", status="succeeded"
        ).first()

        if not payment_tracker or not payment_tracker.stripe_payment_intent_id:
            logger.warning(f"No successful payment tracker found for paid order {order_id}. Cannot refund.")
            return

        refund_amount = payment_tracker.amount
        logger.info(f"Initiating refund of {refund_amount} {payment_tracker.currency} for order {order_id}")

        try:
            # Create refund through Stripe
            stripe_refund = payment_provider.create_refund(
                payment_intent_id=payment_tracker.stripe_payment_intent_id,
                amount=int(refund_amount * 100),  # Convert to cents
                reason="requested_by_customer",
                metadata={
                    "order_id": str(order.id),
                    "cancelled_by": str(user.id),
                    "reason": reason,
                },
            )

            # Create refund tracker
            PaymentTracker.objects.create(
                stripe_refund_id=stripe_refund.id,
                order=order,
                user=user,
                transaction_type="refund",
                status="succeeded",  # Stripe created it, so it's 'succeeded' in terms of initiation
                amount=refund_amount,
                currency="USD",
                notes=f"Order cancelled: {reason}",
            )

            # Update PaymentTransactions to waiting_refund
            payment_transactions = PaymentTransaction.objects.filter(
                order=order,
                status="held",
            )
            for transaction in payment_transactions:
                transaction.status = "waiting_refund"
                refund_note = f"Refund initiated due to order cancellation: {reason} (Amount: ${refund_amount})"
                transaction.notes = f"{transaction.notes}\n{refund_note}" if transaction.notes else refund_note
                transaction.save(update_fields=["status", "notes"])

            logger.info(f"Refund initiated successfully: {stripe_refund.id}")

        except Exception as e:
            logger.error(f"Failed to initiate refund for order {order_id}: {e}")
            # In a real system, we might want to alert an admin or retry

    except Exception as e:
        logger.error(f"Error handling order.cancelled event: {e}", exc_info=True)


def handle_payment_failed(event_data):
    """
    Handle payment.failed event (if we implement it in the future).
    """
    pass


def register_payment_listeners():
    """Register all payment system event listeners."""
    event_bus = get_event_bus()
    event_bus.subscribe("order.cancelled", handle_order_cancelled)
    logger.info("Payment system event listeners registered")
