import logging
from decimal import Decimal
from typing import Any, Dict

from django.contrib.auth import get_user_model
from django.utils import timezone

from marketplace.models import Order
from payment_system.email_utils import (
    send_failed_refund_notification_email,
    send_order_cancellation_receipt_email,
)
from payment_system.infra.payment_provider.stripe_provider import StripePaymentProvider
from payment_system.models import PaymentTracker, PaymentTransaction
from payment_system.security import PaymentAuditLogger
from payment_system.stripe_service import StripeConnectService  # Keep this for now for account.updated webhook
from utils.transaction_utils import atomic_with_isolation, retry_on_deadlock


logger = logging.getLogger(__name__)
User = get_user_model()

# Initialize PaymentProvider for use in webhook service
payment_provider = StripePaymentProvider()


class WebhookService:
    @staticmethod
    def process_event(event: Dict[str, Any], client_ip: str) -> bool:
        """
        Processes a Stripe webhook event, dispatching to appropriate handlers.
        Returns True if the event was handled, False otherwise.
        """
        event_type = event.get("type")
        logger.info(f"WebhookService: Processing event type: {event_type}")

        try:
            if event_type == "checkout.session.completed":
                return WebhookService._handle_checkout_session_completed(event)
            elif event_type == "refund.updated":
                return WebhookService._handle_refund_updated(event)
            elif event_type == "refund.failed":
                return WebhookService._handle_refund_failed(event)
            elif event_type == "account.updated":
                return WebhookService._handle_account_updated(event)
            elif event_type == "transfer.created":
                return WebhookService._handle_transfer_created(event)
            elif event_type == "payment_intent.succeeded":
                return WebhookService._handle_payment_intent_succeeded(event)
            elif event_type == "payment_intent.payment_failed":
                return WebhookService._handle_payment_intent_failed(event)
            else:
                logger.info(f"WebhookService: Unhandled event type: {event_type}")
                return False
        except Exception as e:
            logger.error(f"WebhookService: Error processing event {event_type}: {str(e)}", exc_info=True)
            PaymentAuditLogger.log_security_event(
                "webhook_processing_error_internal",
                client_ip,
                details=f"Internal error for event {event_type}: {str(e)}",
            )
            return False

    @staticmethod
    def _handle_checkout_session_completed(event: Dict[str, Any]) -> bool:
        checkout_session = event["data"]["object"]
        logger.info(f"WebhookService: Checkout session completed: {getattr(checkout_session, 'id', 'unknown')}")

        metadata = getattr(checkout_session, "metadata", {})
        if metadata and metadata.get("user_id"):
            logger.info(f"WebhookService: Found user_id in checkout session metadata: {metadata.get('user_id')}")
            # The original handle_sucessfull_checkout will be moved here or called
            # This logic needs to be moved from views.py
            # For now, it's a placeholder.
            return WebhookService._handle_successful_checkout_logic(checkout_session)
        else:
            logger.warning("WebhookService: No user_id found in checkout session metadata")
            # Fallback to retrieve full session if needed, similar to original views.py logic
            # This logic also needs to be moved from views.py
            session_id = checkout_session.id
            if session_id:
                try:
                    # Use payment_provider to retrieve session (no direct stripe calls)
                    full_session = payment_provider.retrieve_checkout_session(session_id)
                    full_metadata = getattr(full_session, "metadata", {})
                    if full_metadata and full_metadata.get("user_id"):
                        return WebhookService._handle_successful_checkout_logic(full_session)
                except Exception as e:
                    logger.error(f"WebhookService: Error retrieving full session in fallback: {e}")
            return False

    @staticmethod
    def _handle_successful_checkout_logic(session: Dict[str, Any]) -> bool:
        """
        Logic for handling a successful checkout, moved from views.handle_sucessfull_checkout.
        """
        logger.info("WebhookService: Handling successful checkout...")

        try:
            with atomic_with_isolation("READ COMMITTED"):
                user_id = session["metadata"].get("user_id")
                order_id = session["metadata"].get("order_id")

                if not user_id or not order_id:
                    logger.error(
                        f"WebhookService: Missing user_id or order_id in session metadata for {session.get('id')}"
                    )
                    return False

                user = User.objects.get(id=user_id)
                order = Order.objects.select_for_update().get(id=order_id)

                if order.buyer != user:
                    logger.error(f"WebhookService: Order {order_id} does not belong to user {user_id}")
                    return False

                shipping_details = session.get("shipping_details", {})
                customer_details = session.get("customer_details", {})

                shipping_address = {}
                if shipping_details and shipping_details.get("address"):
                    shipping_address = {
                        "name": shipping_details.get("name", ""),
                        "line1": shipping_details["address"].get("line1", ""),
                        "line2": shipping_details["address"].get("line2", ""),
                        "city": shipping_details["address"].get("city", ""),
                        "state": shipping_details["address"].get("state", ""),
                        "postal_code": shipping_details["address"].get("postal_code", ""),
                        "country": shipping_details["address"].get("country", ""),
                    }
                elif customer_details and customer_details.get("address"):
                    shipping_address = {
                        "name": customer_details.get("name", ""),
                        "line1": customer_details["address"].get("line1", ""),
                        "line2": customer_details["address"].get("line2", ""),
                        "city": customer_details["address"].get("city", ""),
                        "state": customer_details["address"].get("state", ""),
                        "postal_code": customer_details["address"].get("postal_code", ""),
                        "country": customer_details["address"].get("country", ""),
                    }

                order.shipping_address = shipping_address
                order.save(update_fields=["shipping_address"])

                payment_intent_id = session.get("payment_intent", "")
                session_id = session.get("id", "")

                if payment_intent_id:
                    existing_trackers = PaymentTracker.objects.filter(
                        stripe_payment_intent_id=payment_intent_id
                    ).select_for_update()

                    if existing_trackers.exists():
                        for tracker in existing_trackers:
                            if tracker.status != "succeeded":
                                tracker.status = "succeeded"
                                tracker.notes = (
                                    f"{tracker.notes}\nUpdated to succeeded via checkout session {session_id}"
                                )
                                tracker.save(update_fields=["status", "notes", "updated_at"])
                    else:
                        PaymentTracker.objects.create(
                            stripe_payment_intent_id=payment_intent_id,
                            order=order,
                            user=user,
                            transaction_type="payment",
                            status="succeeded",
                            amount=order.total_amount,
                            currency="USD",
                            notes=f"Payment completed via checkout session {session_id} for order {order.id} with {order.items.count()} items",
                        )

                if payment_intent_id:
                    existing_transactions = PaymentTransaction.objects.filter(
                        stripe_payment_intent_id=payment_intent_id
                    ).select_for_update()

                    if existing_transactions.exists():
                        for transaction in existing_transactions:
                            if transaction.status != "held":
                                transaction.status = "held"
                                transaction.payment_received_date = timezone.now()
                                transaction.hold_start_date = timezone.now()
                                transaction.planned_release_date = timezone.now() + timezone.timedelta(days=30)
                                transaction.hold_notes = f"Payment succeeded via checkout session {session_id}. Standard 30-day hold period started."
                                transaction.notes = (
                                    f"{transaction.notes}\nPayment succeeded and moved to held status"
                                    if transaction.notes
                                    else "Payment succeeded and moved to held status"
                                )
                                transaction.save(
                                    update_fields=[
                                        "status",
                                        "payment_received_date",
                                        "hold_start_date",
                                        "planned_release_date",
                                        "hold_notes",
                                        "notes",
                                        "updated_at",
                                    ]
                                )
                    else:
                        from collections import defaultdict

                        seller_data = defaultdict(
                            lambda: {"item_count": 0, "item_names": [], "gross_amount": Decimal("0.00")}
                        )

                        for order_item in order.items.all():
                            seller = order_item.seller
                            seller_data[seller]["item_count"] += order_item.quantity
                            seller_data[seller]["item_names"].append(order_item.product_name)
                            seller_data[seller]["gross_amount"] += order_item.total_price

                        for seller, data in seller_data.items():
                            gross_amount = data["gross_amount"]
                            platform_fee = gross_amount * Decimal("0.03")
                            stripe_fee = (gross_amount * Decimal("0.029")) + Decimal("0.30")
                            net_amount = gross_amount - platform_fee - stripe_fee

                            PaymentTransaction.objects.create(
                                stripe_payment_intent_id=payment_intent_id,
                                stripe_checkout_session_id=session_id,
                                order=order,
                                seller=seller,
                                buyer=order.buyer,
                                status="held",
                                gross_amount=gross_amount,
                                platform_fee=platform_fee,
                                stripe_fee=stripe_fee,
                                net_amount=net_amount,
                                currency="USD",
                                item_count=data["item_count"],
                                item_names=", ".join(data["item_names"]),
                                payment_received_date=timezone.now(),
                                hold_reason="standard",
                                days_to_hold=30,
                                hold_start_date=timezone.now(),
                                hold_notes="Standard 30-day hold period for marketplace transactions",
                                notes=f"Payment succeeded via checkout session {session_id} for order {order.id}",
                                metadata={
                                    "order_id": str(order.id),
                                    "payment_intent_id": payment_intent_id,
                                    "checkout_session_id": session_id,
                                    "seller_id": str(seller.id),
                                    "buyer_id": str(order.buyer.id),
                                    "completed_at": str(timezone.now()),
                                },
                            )
            return True
        except User.DoesNotExist:
            logger.error(f"WebhookService: User not found for session {session.get('id')}")
            return False
        except Order.DoesNotExist:
            logger.error(f"WebhookService: Order not found for session {session.get('id')}")
            return False
        except Exception as e:
            logger.error(
                f"WebhookService: Error handling successful checkout for session {session.get('id')}: {str(e)}"
            )
            return False

    @staticmethod
    def _handle_refund_updated(event: Dict[str, Any]) -> bool:
        refund_object = event["data"]["object"]
        logger.info(
            f"WebhookService: Refund updated event received for refund_id: {getattr(refund_object, 'id', 'unknown')}"
        )

        refund_id = getattr(refund_object, "id", "")
        refund_status = getattr(refund_object, "status", "")
        refund_amount = getattr(refund_object, "amount", 0) / 100
        refund_metadata = getattr(refund_object, "metadata", {})

        if refund_status == "succeeded" and getattr(refund_object, "failure_balance_transaction", None) is None:
            order_id = refund_metadata.get("order_id")
            if order_id:
                try:
                    with atomic_with_isolation("READ COMMITTED"):
                        order = Order.objects.get(id=order_id)
                        order.status = "refunded"
                        order.payment_status = "refunded"
                        order.save(update_fields=["status", "payment_status"])

                        for item in order.items.all():
                            product = item.product
                            product.stock_quantity += item.quantity
                            product.save(update_fields=["stock_quantity"])

                        payment_transactions = PaymentTransaction.objects.filter(order=order, status="waiting_refund")
                        for transaction in payment_transactions:
                            transaction.status = "refunded"
                            transaction.notes = (
                                f"{transaction.notes}\nRefund succeeded via webhook: {refund_id}"
                                if transaction.notes
                                else f"Refund succeeded via webhook: {refund_id}"
                            )
                            transaction.save(update_fields=["status", "notes", "updated_at"])

                        existing_tracker = PaymentTracker.objects.filter(stripe_refund_id=refund_id).first()
                        if existing_tracker:
                            existing_tracker.status = "success_refund"
                            existing_tracker.notes = f"{existing_tracker.notes}\nRefund succeeded: {refund_metadata.get('reason', 'Order cancelled')}"
                            existing_tracker.save(update_fields=["status", "notes", "updated_at"])
                        else:
                            PaymentTracker.objects.create(
                                stripe_refund_id=refund_id,
                                order=order,
                                user=order.buyer,
                                transaction_type="refund",
                                status="success_refund",
                                amount=refund_amount,
                                currency="USD",
                                notes=f"Refund succeeded: {refund_metadata.get('reason', 'Order cancelled')}",
                            )

                        _cancelled_by_id = refund_metadata.get("cancelled_by")
                        cancellation_reason = refund_metadata.get("reason", "Order cancelled")
                        send_order_cancellation_receipt_email(order, cancellation_reason, refund_amount)

                    return True
                except Order.DoesNotExist:
                    logger.error(f"WebhookService: Order {order_id} not found for refund updated event.")
                    return False
                except Exception as e:
                    logger.error(f"WebhookService: Error processing refund.updated for order {order_id}: {str(e)}")
                    return False
        return False

    @staticmethod
    def _handle_refund_failed(event: Dict[str, Any]) -> bool:
        refund_object = event["data"]["object"]
        logger.info(
            f"WebhookService: Refund failed event received for refund_id: {getattr(refund_object, 'id', 'unknown')}"
        )

        refund_id = getattr(refund_object, "id", "")
        failure_reason = getattr(refund_object, "failure_reason", "Unknown")
        refund_amount = getattr(refund_object, "amount", 0) / 100
        refund_metadata = getattr(refund_object, "metadata", {})

        order_id = refund_metadata.get("order_id")
        if order_id:
            try:
                with atomic_with_isolation("READ COMMITTED"):
                    order = Order.objects.get(id=order_id)
                    order.status = "cancelled"
                    order.payment_status = "failed_refund"
                    order.save(update_fields=["status", "payment_status"])

                    payment_transactions = PaymentTransaction.objects.filter(order=order, status="waiting_refund")
                    for transaction in payment_transactions:
                        transaction.status = "failed_refund"
                        transaction.notes = (
                            f"{transaction.notes}\nRefund failed via webhook: {refund_id} - {failure_reason}"
                            if transaction.notes
                            else f"Refund failed via webhook: {refund_id} - {failure_reason}"
                        )
                        transaction.save(update_fields=["status", "notes", "updated_at"])

                    existing_tracker = PaymentTracker.objects.filter(stripe_refund_id=refund_id).first()
                    if existing_tracker:
                        existing_tracker.status = "failed_refund"
                        existing_tracker.notes = f"{existing_tracker.notes}\nRefund failed: {failure_reason}"
                        existing_tracker.save(update_fields=["status", "notes", "updated_at"])
                    else:
                        PaymentTracker.objects.create(
                            stripe_refund_id=refund_id,
                            order=order,
                            user=order.buyer,
                            transaction_type="refund",
                            status="failed_refund",
                            amount=refund_amount,
                            currency="USD",
                            notes=f"Refund failed: {failure_reason}",
                        )

                    send_failed_refund_notification_email(order, failure_reason, refund_amount)
                return True
            except Order.DoesNotExist:
                logger.error(f"WebhookService: Order {order_id} not found for refund failed event.")
                return False
            except Exception as e:
                logger.error(f"WebhookService: Error processing refund.failed for order {order_id}: {str(e)}")
                return False
        return False  # Fallback logic is complex, might need to be re-evaluated later

    @staticmethod
    def _handle_account_updated(event: Dict[str, Any]) -> bool:
        account_object = event["data"]["object"]
        account_id = getattr(account_object, "id", "")
        logger.info(f"WebhookService: Account updated event received for account: {account_id}")

        try:
            # Import the service here to avoid circular imports
            # from payment_system.stripe_service import StripeConnectService
            # Process the account update
            result = StripeConnectService.handle_account_updated_webhook(account_id, account_object)
            if not result["success"]:
                logger.warning(f"WebhookService: Failed to process account update: {result['errors']}")
            return result["success"]
        except Exception as e:
            logger.error(f"WebhookService: Error processing account.updated webhook: {str(e)}")
            return False

    @staticmethod
    def _handle_transfer_created(event: Dict[str, Any]) -> bool:
        transfer_object = event["data"]["object"]
        logger.info(
            f"WebhookService: Transfer created event received for ID: {getattr(transfer_object, 'id', 'unknown')}"
        )

        transfer_id = getattr(transfer_object, "id", "")
        amount = getattr(transfer_object, "amount", 0)
        currency = getattr(transfer_object, "currency", "")
        destination = getattr(transfer_object, "destination", "")
        metadata = getattr(transfer_object, "metadata", {})
        reversed = getattr(transfer_object, "reversed", False)

        transaction_id = metadata.get("transaction_id")
        order_id = metadata.get("order_id")
        seller_id = metadata.get("seller_id")

        if transaction_id:
            try:

                @retry_on_deadlock(max_retries=3, delay=0.01, backoff=2.0)
                def process_transfer_success():
                    return PaymentTransaction.objects.get(id=transaction_id)

                payment_transaction = process_transfer_success()

                with atomic_with_isolation("READ COMMITTED"):
                    order = Order.objects.get(id=order_id)
                    seller = User.objects.get(id=seller_id)
                    PaymentTracker.objects.create(
                        stripe_transfer_id=transfer_id,
                        order=order,
                        user=seller,
                        transaction_type="transfer",
                        status="succeeded",
                        amount=Decimal(amount) / 100,
                        currency=currency.upper(),
                        notes=f"Transfer to seller {seller.username} for order {order.id} created successfully.",
                    )

                    if not reversed:
                        transaction_for_update = PaymentTransaction.objects.select_for_update().get(id=transaction_id)
                        if transaction_for_update.status == "processing":
                            transaction_for_update.status = "released"
                            transaction_for_update.actual_release_date = timezone.now()
                            transaction_for_update.transfer_id = transfer_id
                            transaction_for_update.notes = (
                                f"{transaction_for_update.notes}\nTransfer succeeded via webhook: {transfer_id} (amount: {amount / 100:.2f} {currency.upper()})"
                                if transaction_for_update.notes
                                else f"Transfer succeeded via webhook: {transfer_id} (amount: {amount / 100:.2f} {currency.upper()})"
                            )
                            transaction_for_update.save(
                                update_fields=["status", "actual_release_date", "transfer_id", "notes", "updated_at"]
                            )

                            existing_tracker = (
                                PaymentTracker.objects.filter(stripe_transfer_id=transfer_id)
                                .select_for_update()
                                .first()
                            )
                            if existing_tracker:
                                existing_tracker.status = "succeeded"
                                existing_tracker.save(update_fields=["status", "updated_at"])

                        if hasattr(payment_transaction, "metadata") and payment_transaction.metadata:
                            transaction_for_metadata = PaymentTransaction.objects.select_for_update().get(
                                id=transaction_id
                            )
                            transaction_for_metadata.metadata.update(
                                {
                                    "webhook_transfer_id": transfer_id,
                                    "webhook_received": timezone.now().isoformat(),
                                    "webhook_amount": amount,
                                    "webhook_currency": currency,
                                    "webhook_destination": destination,
                                    "webhook_event_type": "transfer.created",
                                    "transfer_success_status": "released",
                                }
                            )
                            transaction_for_metadata.save(update_fields=["metadata", "updated_at"])
                return True
            except PaymentTransaction.DoesNotExist:
                logger.error(
                    f"WebhookService: Payment transaction {transaction_id} not found for transfer created event."
                )
                return False
            except Exception as e:
                logger.error(
                    f"WebhookService: Error processing transfer.created for transaction {transaction_id}: {str(e)}"
                )
                return False
        return False

    @staticmethod
    def _handle_payment_intent_succeeded(event: Dict[str, Any]) -> bool:
        payment_intent = event["data"]["object"]
        logger.info(
            f"WebhookService: payment_intent.succeeded received for ID: {getattr(payment_intent, 'id', 'unknown')}"
        )

        # Need to move handle_payment_intent_succeeded here
        # For now, assuming it's a standalone function. It's not in the provided views.py snippet
        # Placeholder call
        # result = handle_payment_intent_succeeded(payment_intent)
        # return result["success"]
        logger.warning("WebhookService: handle_payment_intent_succeeded not yet implemented.")
        return False

    @staticmethod
    def _handle_payment_intent_failed(event: Dict[str, Any]) -> bool:
        payment_intent = event["data"]["object"]
        logger.info(
            f"WebhookService: payment_intent.payment_failed received for ID: {getattr(payment_intent, 'id', 'unknown')}"
        )

        # Need to move handle_payment_intent_failed here
        # For now, assuming it's a standalone function. It's not in the provided views.py snippet
        # Placeholder call
        # result = handle_payment_intent_failed(payment_intent)
        # return result["success"]
        logger.warning("WebhookService: handle_payment_intent_failed not yet implemented.")
        return False
