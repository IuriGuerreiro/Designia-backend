import logging
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import OpenApiResponse, OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from marketplace.models import Cart, Order, OrderItem
from payment_system.api.serializers.request_serializers import (
    OrderCancellationRequestSerializer,
    StripeAccountCreateRequestSerializer,
    TransferRequestSerializer,
)
from payment_system.api.serializers.response_serializers import (
    CheckoutSessionResponseSerializer,
    ErrorResponseSerializer,
    OrderCancellationResponseSerializer,
    StripeAccountSessionResponseSerializer,
    StripeAccountStatusResponseSerializer,
    TransferResponseSerializer,
)
from payment_system.domain.services import stripe_events
from payment_system.domain.services.security_service import PaymentAuditLogger
from payment_system.domain.services.webhook_service import WebhookService
from payment_system.infra.observability.metrics import payout_volume_total
from payment_system.infra.payment_provider.stripe_provider import StripePaymentProvider
from payment_system.models import PaymentTracker, PaymentTransaction, Payout, PayoutItem
from utils.transaction_utils import (
    DeadlockError,
    TransactionError,
    atomic_with_isolation,
    financial_transaction,
    get_current_isolation_level,
    retry_on_deadlock,
    rollback_safe_operation,
)


# Initialize PaymentProvider
payment_provider = StripePaymentProvider()

# Initialize logger
logger = logging.getLogger(__name__)

User = get_user_model()


# Handle Stripe webhook events VERY VERY IMPORTANTE
@method_decorator(csrf_exempt, name="dispatch")
class StripeWebhookView(View):
    """Process Stripe webhooks - thin router that delegates to WebhookService."""

    @extend_schema(
        operation_id="payment_stripe_webhook",
        summary="Stripe Webhook Endpoint",
        description="Endpoint for receiving Stripe webhook events. Verifies signature and processes events.",
        request=OpenApiTypes.OBJECT,
        responses={
            200: OpenApiResponse(description="Webhook processed successfully"),
            400: OpenApiResponse(description="Invalid payload or signature"),
            500: OpenApiResponse(description="Processing error"),
        },
        tags=["Webhooks"],
        auth=[],
    )
    @method_decorator(financial_transaction)
    def post(self, request):  # noqa: C901
        """Process Stripe webhooks.

        Summary:
        - Verifies webhook signatures and logs security events.
        - Delegates all event processing to WebhookService.process_event()
        - Returns appropriate HTTP response based on processing result.
        """
        payload = request.body
        endpoint_secret = settings.STRIPE_WEBHOOK_SECRET
        sig_header = request.headers.get("stripe-signature")

        # Get client IP for security monitoring
        client_ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0] or request.META.get(
            "REMOTE_ADDR", "unknown"
        )

        # SECURITY FIX: Always require webhook signature verification
        if not endpoint_secret:
            PaymentAuditLogger.log_security_event(
                "webhook_missing_secret",
                client_ip,
                details="STRIPE_WEBHOOK_SECRET not configured - critical security vulnerability",
            )
            logger.error("Critical Security Error: STRIPE_WEBHOOK_SECRET not configured. Rejecting webhook.")
            return HttpResponse(
                status=500,
                content="Webhook endpoint secret must be configured for security. Contact system administrator.".encode(
                    "utf-8"
                ),
            )

        if not sig_header:
            PaymentAuditLogger.log_security_event(
                "webhook_missing_signature", client_ip, details="Webhook request without stripe-signature header"
            )
            logger.warning(f"Webhook rejected: Missing stripe-signature header from IP {client_ip}")
            return HttpResponse(
                status=400, content="Missing stripe-signature header. Webhook verification required.".encode("utf-8")
            )

        # SECURITY: Verify webhook signature BEFORE processing any data
        try:
            event = payment_provider.verify_webhook(payload, sig_header, endpoint_secret)
            # Log successful webhook verification
            PaymentAuditLogger.log_security_event(
                "webhook_verified",
                client_ip,
                details=f"Successful webhook verification for event: {event.get('type', 'unknown')}",
            )
            logger.info(
                f"Webhook signature verified successfully for event: {event.get('type', 'unknown')} from IP {client_ip}"
            )
            # Delegate safe event logging to service layer (no payloads)
            try:
                stripe_events.handle_event(event)
            except Exception:  # pragma: no cover - defensive logging only
                logger.warning("Stripe event logging via service failed; continuing")
        except ValueError as e:  # Catch ValueErrors from payment_provider.verify_webhook
            PaymentAuditLogger.log_security_event(
                "webhook_signature_failed",
                client_ip,
                details=f"Signature verification or payload parsing failed: {str(e)}",
            )
            logger.warning(f"Webhook signature or payload verification failed from IP {client_ip}: {str(e)}")
            return HttpResponse(status=400, content=f"Webhook verification failed: {str(e)}".encode("utf-8"))
        except Exception as e:
            PaymentAuditLogger.log_security_event(
                "webhook_processing_error", client_ip, details=f"Unexpected error: {str(e)}"
            )
            logger.error(f"Unexpected webhook verification error from IP {client_ip}: {str(e)}")
            return HttpResponse(status=500, content="Webhook processing error.".encode("utf-8"))

        # Delegate all event processing to WebhookService
        logger.info(f"🔔 Received Stripe event: {event.get('type', 'unknown')}")

        try:
            handled = WebhookService.process_event(event, client_ip)
            if handled:
                logger.info(f"✅ Event {event.get('type')} processed successfully by WebhookService")
                return HttpResponse(
                    status=200, content=f"{event.get('type')} event successfully processed".encode("utf-8")
                )
            else:
                logger.info(f"ℹ️  Event {event.get('type')} received but not handled by WebhookService")
                return HttpResponse(
                    status=200, content=f"{event.get('type')} event received but not processed".encode("utf-8")
                )
        except Exception as e:
            logger.error(f"❌ Error processing event {event.get('type')} via WebhookService: {str(e)}", exc_info=True)
            PaymentAuditLogger.log_security_event(
                "webhook_service_error",
                client_ip,
                details=f"WebhookService failed to process {event.get('type')}: {str(e)}",
            )
            # Return 200 to prevent Stripe retries for application errors
            return HttpResponse(status=200, content=f"{event.get('type')} event processing failed".encode("utf-8"))


def update_payment_trackers_for_payout(payout, event_type):  # noqa: C901
    """Update PaymentTracker records for a payout webhook.

    This function normalizes tracker status for transactions included in the payout,
    creating or updating PaymentTracker rows for each related PaymentTransaction using
    READ COMMITTED isolation to keep updates consistent under concurrency.
    """
    try:
        from .models import PaymentTracker, PayoutItem

        # Determine the new tracker status based on event and payout status
        if event_type == "payout.paid" or payout.status == "paid":
            new_status = "payout_success"
            success_msg = f"  PaymentTracker updated to payout_success for payout {payout.id}"
        elif event_type == "payout.failed" or payout.status == "failed":
            new_status = "payout_failed"
            success_msg = f" PaymentTracker updated to payout_failed for payout {payout.id}"
        elif payout.status == "pending":
            new_status = "pending"
            success_msg = f"⏳ PaymentTracker updated to pending for payout {payout.id}"
        else:
            # For other statuses (in_transit, canceled, etc.), mark as pending
            new_status = "pending"
            success_msg = f"📊 PaymentTracker updated to pending for payout {payout.id} (status: {payout.status})"

        with atomic_with_isolation("READ COMMITTED"):
            # Find PaymentTransactions associated with this payout through PayoutItems
            payout_items = PayoutItem.objects.filter(payout=payout).select_related("payment_transfer")

            created_count = 0
            updated_count = 0

            # Process each transaction in this payout
            for payout_item in payout_items:
                transaction_obj = payout_item.payment_transfer

                if transaction_obj:
                    # Find existing PaymentTracker records for this transaction and seller
                    stripe_intent_id = transaction_obj.stripe_payment_intent_id or f"payout_{transaction_obj.id}"
                    existing_trackers = PaymentTracker.objects.filter(
                        stripe_payment_intent_id=stripe_intent_id, user=payout.seller, transaction_type="payout"
                    )

                    if existing_trackers.exists():
                        # Update all existing trackers for this transaction
                        update_count = existing_trackers.update(status=new_status, updated_at=timezone.now())
                        updated_count += update_count
                        print(
                            f"  Updated {update_count} PaymentTracker(s) for transaction {transaction_obj.id} (status: {new_status})"
                        )
                        logger.info(
                            f"Updated {update_count} PaymentTracker records to {new_status} for payout {payout.id} transaction {transaction_obj.id}"
                        )

                        # Update notes on each tracker individually (bulk update doesn't support notes concatenation)
                        for tracker in existing_trackers:
                            tracker.notes = (
                                f"{tracker.notes}\nPayout {event_type}: {payout.stripe_payout_id}"
                                if tracker.notes
                                else f"Payout {event_type}: {payout.stripe_payout_id}"
                            )
                            tracker.save(update_fields=["notes"])
                    else:
                        # Create new PaymentTracker if none exist
                        tracker = PaymentTracker.objects.create(
                            stripe_payment_intent_id=stripe_intent_id,
                            user=payout.seller,
                            status=new_status,
                            amount=transaction_obj.gross_amount,
                            currency=transaction_obj.currency,
                            order=transaction_obj.order,
                            transaction_type="payout",
                            notes=f"Payout {event_type}: {payout.stripe_payout_id}",
                            created_at=timezone.now(),
                        )
                        created_count += 1
                        print(
                            f"  Created PaymentTracker {tracker.id} for transaction {transaction_obj.id} (status: {new_status})"
                        )
                        logger.info(
                            f"Created PaymentTracker {tracker.id} for payout {payout.id} transaction {transaction_obj.id}"
                        )
                else:
                    print(f"⚠️ PayoutItem {payout_item.id} has no associated payment_transfer")
                    logger.warning(f"PayoutItem {payout_item.id} in payout {payout.id} has no payment_transfer")

            # Fallback: if no PayoutItems found, try to find related transactions by seller
            if not payout_items.exists():
                print(f"⚠️ No PayoutItems found for payout {payout.id}, trying fallback approach")
                logger.warning(f"No PayoutItems found for payout {payout.id}, attempting fallback tracker search")

                # Find existing trackers by seller that might be related to this payout
                related_trackers = PaymentTracker.objects.filter(
                    user=payout.seller, status__in=["payout_processing", "pending"], transaction_type="payout"
                ).select_for_update()

                for tracker in related_trackers:
                    # Basic validation: currency match
                    if tracker.currency == payout.currency:
                        tracker.status = new_status
                        tracker.notes = (
                            f"{tracker.notes}\nPayout {event_type}: {payout.stripe_payout_id}"
                            if tracker.notes
                            else f"Payout {event_type}: {payout.stripe_payout_id}"
                        )
                        tracker.save(update_fields=["status", "notes", "updated_at"])
                        updated_count += 1
                        print(f"  Updated PaymentTracker {tracker.id} via fallback method (status: {new_status})")
                        logger.info(f"Updated PaymentTracker {tracker.id} via fallback for payout {payout.id}")

            total_processed = created_count + updated_count
            if total_processed > 0:
                print(success_msg + f" ({created_count} created, {updated_count} updated)")
                logger.info(
                    f"Processed {total_processed} PaymentTracker records for payout {payout.id}: {created_count} created, {updated_count} updated"
                )
            else:
                print(f"ℹ️ No PaymentTracker records processed for payout {payout.id}")
                logger.info(f"No PaymentTracker records found or created for payout {payout.id}")

    except Exception as e:
        logger.error(f"Error updating PaymentTracker records for payout {payout.id}: {str(e)}")
        print(f" Error updating PaymentTracker records: {str(e)}")
        # Don't fail the webhook for tracker update errors


def create_payout_from_webhook(stripe_payout_id, payout_object, event_type):
    """Create a Payout from Stripe webhook data when missing.

    This function extracts seller and payout details from the Stripe payload, resolves the
    seller, persists a Payout record with metadata for auditability, and triggers tracker
    updates for included transactions.
    """
    try:
        # Extract payout data from Stripe object
        payout_amount = getattr(payout_object, "amount", 0)
        payout_currency = getattr(payout_object, "currency", "EUR").upper()
        payout_status = getattr(payout_object, "status", "pending")
        payout_created = getattr(payout_object, "created", None)
        payout_arrival_date = getattr(payout_object, "arrival_date", None)
        payout_description = getattr(payout_object, "description", "")
        payout_metadata = getattr(payout_object, "metadata", {})

        # Try to determine seller from metadata or description
        seller_id = payout_metadata.get("seller_id") or payout_metadata.get("user_id")

        if not seller_id:
            # Try to extract from description or find from existing PaymentTransactions
            logger.warning(f"No seller_id found in payout metadata for {stripe_payout_id}")
            print(f"⚠️ No seller_id in payout metadata for {stripe_payout_id}")

            # Try to find seller from existing PaymentTransactions that might be included
            from django.contrib.auth import get_user_model

            from .models import PaymentTransaction

            User = get_user_model()

            # Look for PaymentTransactions that match this payout amount and currency
            # This is a fallback approach when seller info is missing
            try:
                potential_transactions = PaymentTransaction.objects.filter(
                    gross_amount=Decimal(payout_amount) / 100,  # Convert from cents
                    currency=payout_currency,
                    payed_out=False,
                    status__in=["completed", "released"],
                ).select_related("seller")
            except Exception as tx_error:
                logger.error(f"Error querying PaymentTransactions for fallback seller: {tx_error}")
                print(f" Error finding fallback seller: {tx_error}")
                potential_transactions = PaymentTransaction.objects.none()

            if potential_transactions.exists():
                # Use the seller from the first matching transaction
                seller = potential_transactions.first().seller
                logger.info(f"Found potential seller {seller.id} for payout {stripe_payout_id}")
                print(f"🔍 Found potential seller: {seller.username}")
            else:
                logger.error(f"Cannot determine seller for payout {stripe_payout_id}")
                print(f" Cannot determine seller for payout {stripe_payout_id}")
                return None
        else:
            # Get seller from metadata
            from django.contrib.auth import get_user_model

            User = get_user_model()
            try:
                seller = User.objects.get(id=seller_id)
                logger.info(f"Found seller {seller.id} from metadata for payout {stripe_payout_id}")
                print(f"  Found seller from metadata: {seller.username}")
            except User.DoesNotExist:
                logger.error(f"Seller {seller_id} not found for payout {stripe_payout_id}")
                print(f" Seller {seller_id} not found for payout {stripe_payout_id}")
                return None

        # Import Payout model
        from .models import Payout

        # Create the payout record using READ COMMITTED isolation
        with atomic_with_isolation("READ COMMITTED"):
            payout_record = Payout.objects.create(
                stripe_payout_id=stripe_payout_id,
                seller=seller,
                status=payout_status,
                payout_type="standard",  # Default type for webhook-created payouts
                amount_cents=payout_amount,
                currency=payout_currency,
                stripe_created_at=(
                    timezone.datetime.fromtimestamp(payout_created, tz=timezone.get_current_timezone())
                    if payout_created
                    else timezone.now()
                ),
                arrival_date=(
                    timezone.datetime.fromtimestamp(payout_arrival_date, tz=timezone.get_current_timezone())
                    if payout_arrival_date
                    else None
                ),
                description=payout_description or f"Webhook-created payout for seller {seller.username}",
                metadata={
                    "created_via_webhook": True,
                    "webhook_event_type": event_type,
                    "original_stripe_metadata": dict(payout_metadata),
                    "seller_id": str(seller.id),
                    "webhook_created_at": timezone.now().isoformat(),
                },
            )

            logger.info(f"Successfully created payout {payout_record.id} from webhook for seller {seller.id}")
            print(f"  Created payout record: {payout_record.id}")
            print(f"   Stripe Payout ID: {stripe_payout_id}")
            print(f"   Seller: {seller.username}")
            print(f"   Amount: {payout_record.amount_formatted}")
            print(f"   Status: {payout_status}")

            # Update PaymentTracker records for this new payout
            update_payment_trackers_for_payout(payout_record, event_type)

            return payout_record

    except Exception as e:
        logger.error(f"Failed to create payout from webhook {stripe_payout_id}: {str(e)}")
        print(f" Failed to create payout from webhook: {str(e)}")
        return None


def update_payout_from_webhook(event, payout_object):  # noqa: C901
    """Update a Payout from Stripe webhook events.

    This function locks and updates the Payout, sets status (paid/failed/etc.), updates
    arrival dates, resets related transaction flags on failure, and uses transaction
    helpers with deadlock retries to maintain consistency.
    """
    stripe_payout_id = getattr(payout_object, "id", None)
    payout_status = getattr(payout_object, "status", None)
    payout_arrival_date = getattr(payout_object, "arrival_date", None)

    # Log current isolation level for debugging
    current_isolation = get_current_isolation_level()
    print(f"🔐 Webhook isolation level: {current_isolation}")
    logger.info(
        f"Webhook payout update started for payout {stripe_payout_id} with isolation level: {current_isolation}"
    )

    if not stripe_payout_id:
        logger.warning("[WARNING] No stripe_payout_id found in payout object")
        print("⚠️ No stripe_payout_id found in payout object")
        return None

    # Define a deadlock-safe operation for complete payout update in a single SERIALIZABLE transaction
    @retry_on_deadlock(max_retries=3, delay=0.01, backoff=2.0)  # 10ms initial delay
    def update_payout_safe():  # noqa: C901
        """Perform the complete payout update inside one transaction with deadlock retries."""
        with atomic_with_isolation("READ COMMITTED"):
            with rollback_safe_operation("Complete Payout Webhook Update"):
                try:
                    # Step 1: Retrieve payout with row-level locking for consistency
                    payout = Payout.objects.select_for_update().get(stripe_payout_id=stripe_payout_id)
                    logger.info(f"[WEBHOOK] Found payout {payout.id} for Stripe payout {stripe_payout_id}")
                    print(f"  Found Payout: {payout.id}")
                    print(f"   Current status: {payout.status}")
                    print(f"   Amount: {payout.amount_formatted}")
                    print(f"   Seller: {payout.seller.username}")

                    # Step 2: Handle specific payout events according to requirements
                    if event.type in ["payout.paid"]:
                        # For payout updated and paid events, set status to 'paid' as requested
                        payout.status = "paid"
                        print(f"🎯 Setting payout status to 'paid' for event type: {event.type}")
                        logger.info(f"[WEBHOOK] Setting payout {payout.id} status to 'paid' for event {event.type}")
                    else:
                        # For other events, use the actual Stripe status
                        payout.status = payout_status
                        print(f"📊 Setting payout status to '{payout_status}' for event type: {event.type}")

                    # Step 3: Update arrival date if provided
                    if payout_arrival_date:
                        payout.arrival_date = timezone.datetime.fromtimestamp(
                            payout_arrival_date, tz=timezone.get_current_timezone()
                        )

                    # Step 4: Handle failure information and transaction resets
                    if event.type == "payout.failed":
                        failure_code = getattr(payout_object, "failure_code", None)
                        failure_message = getattr(payout_object, "failure_message", None)

                        payout.failure_code = failure_code or "unknown"
                        payout.failure_message = failure_message or "Payout failed"

                        logger.error(f"[WEBHOOK] Payout {payout.id} failed: {failure_code} - {failure_message}")
                        print(f" Payout failed: {failure_code} - {failure_message}")

                        # Log failure for monitoring
                        print(f" Payout {payout.id} failed: {failure_code} - {failure_message}")

                        # Step 5: Reset payed_out flag for all transactions in this failed payout atomically
                        # Query payout items with row-level locking within the same transaction
                        payout_items = (
                            PayoutItem.objects.select_for_update()
                            .filter(payout=payout)
                            .select_related("payment_transfer")
                        )

                        transaction_ids = []
                        for payout_item in payout_items:
                            if payout_item.payment_transfer and payout_item.payment_transfer.payed_out:
                                transaction_ids.append(payout_item.payment_transfer.id)

                        # Bulk reset transactions within the same SERIALIZABLE transaction
                        if transaction_ids:
                            reset_count = PaymentTransaction.objects.filter(
                                id__in=transaction_ids, payed_out=True
                            ).update(payed_out=False, actual_release_date=None)

                            logger.info(
                                f"[PAYOUT_FAILED] Reset {reset_count} transaction flags for payout {payout.id} (PayoutItems preserved for audit)"
                            )
                            print(
                                f"🔄 Reset {reset_count} transaction flags for failed payout (PayoutItems kept for audit trail)"
                            )

                        # Update payout with failure information
                        payout.save(
                            update_fields=["status", "failure_code", "failure_message", "arrival_date", "updated_at"]
                        )
                    else:
                        # Step 6: Update payout status for successful events
                        payout.save(update_fields=["status", "arrival_date", "updated_at"])

                    # Step 7: Update metadata with webhook information atomically
                    if hasattr(payout, "metadata") and payout.metadata:
                        payout.metadata.update(
                            {
                                "webhook_event_type": event.type,
                                "webhook_received": timezone.now().isoformat(),
                                "webhook_status": payout.status,
                                "webhook_arrival_date": payout_arrival_date,
                                "last_webhook_event_id": getattr(event, "id", "unknown"),
                            }
                        )
                        payout.save(update_fields=["metadata", "updated_at"])
                        print("📝 Updated payout metadata with webhook info")

                    # Step 8: Mark related transfers as paid out when payout is successful
                    if event.type in ["payout.paid"] and payout.status == "paid":
                        print("🎯 Payout marked as paid, updating related transfers...")

                        if event.type == "payout.updated" and payout.status != "paid":
                            print("⚠️ Payout updated but not marked as paid, skipping transfer updates")
                            return payout

                        # Query payout items with row-level locking within the same transaction
                        payout_items = payout.payout_items.select_for_update().select_related("payment_transfer")
                        transfers_updated = 0

                        for payout_item in payout_items:
                            payment_transfer = payout_item.payment_transfer
                            if payment_transfer and not payment_transfer.payed_out:
                                payment_transfer.payed_out = True
                                payment_transfer.save(update_fields=["payed_out", "updated_at"])
                                transfers_updated += 1
                                print(f"💰 Marked transfer {payment_transfer.id} as paid out")
                                # Increment payout volume metric
                                payout_volume_total.labels(currency=payout.currency, status="paid").inc(
                                    float(payment_transfer.net_amount)
                                )

                        logger.info(
                            f"[SUCCESS] Marked {transfers_updated} transfers as paid out for payout {payout.id}"
                        )
                        print(f"  Updated {transfers_updated} payment transfers to payed_out=True")

                    logger.info(f"[SUCCESS] Payout {payout.id} updated with status: {payout.status}")
                    print(f"  Payout status updated to: {payout.status}")

                    # Update PaymentTracker records based on payout status
                    update_payment_trackers_for_payout(payout, event.type)

                    return payout

                except Payout.DoesNotExist:
                    logger.warning(
                        f"[CREATE] Payout with stripe_payout_id {stripe_payout_id} not found, creating new one"
                    )
                    print(f"🔄 Payout {stripe_payout_id} not found in database, creating new payout...")

                    # Create new payout from webhook data
                    new_payout = create_payout_from_webhook(stripe_payout_id, payout_object, event.type)

                    if new_payout:
                        logger.info(f"[SUCCESS] Created new payout {new_payout.id} from webhook")
                        print(f"  Successfully created new payout: {new_payout.id}")
                        return new_payout
                    else:
                        logger.error(f"[ERROR] Failed to create payout from webhook for {stripe_payout_id}")
                        print(" Failed to create payout from webhook")
                        raise TransactionError(
                            f"Failed to create payout for stripe_payout_id {stripe_payout_id}"
                        ) from None
                except Exception as e:
                    logger.error(f"[ERROR] Unexpected error updating payout {stripe_payout_id}: {str(e)}")
                    print(f" Error updating payout: {str(e)}")
                    # Re-raise as TransactionError to trigger rollback
                    raise TransactionError(f"Failed to update payout {stripe_payout_id}: {str(e)}") from e

    # Execute the complete payout update with deadlock protection
    try:
        updated_payout = update_payout_safe()
        return updated_payout

    except DeadlockError as e:
        logger.error(f"Deadlock error in update_payout_from_webhook after retries: {e}")
        # Return None to indicate failure - caller should handle gracefully
        print(f" Webhook payout update failed due to deadlock: {e}")
        return None

    except TransactionError as e:
        logger.error(f"Transaction error in update_payout_from_webhook: {e}")
        # Return None to indicate failure - caller should handle gracefully
        print(f" Webhook payout update failed due to transaction error: {e}")
        return None

    except Exception as e:
        logger.error(f"Unexpected error in update_payout_from_webhook: {str(e)}", exc_info=True)
        return None


@extend_schema(
    operation_id="payment_stripe_webhook_connect",
    summary="Stripe Connect Webhook Endpoint",
    description="Endpoint for receiving Stripe Connect webhook events. Verifies signature and processes events.",
    request=OpenApiTypes.OBJECT,
    responses={
        200: OpenApiResponse(description="Webhook processed successfully"),
        400: OpenApiResponse(description="Invalid payload or signature"),
    },
    tags=["Webhooks"],
    auth=[],
)
def stripe_webhook_connect(request):  # noqa: C901
    """Handle Stripe Connect webhooks for seller accounts and payouts.

    This function verifies the Connect signature, routes payout-related events to the
    payout updater with transaction safety, and logs errors without failing the webhook.
    """
    payload = request.body
    endpoint_secret = settings.STRIPE_WEBHOOK_CONNECT_SECRET
    sig_header = request.headers.get("stripe-signature")

    event = None

    try:
        event = payment_provider.verify_webhook(payload, sig_header, endpoint_secret)
        logger.info("Stripe Connect event constructed and verified (type=%s)", getattr(event, "type", "unknown"))
    except ValueError as e:  # Catch ValueErrors from payment_provider.verify_webhook
        logger.warning("Stripe Connect webhook signature verification or payload parsing failed: %s", str(e))
        return HttpResponse(status=400, content=f"Webhook verification failed: {str(e)}".encode("utf-8"))
    except Exception as e:
        logger.error("Error processing Stripe Connect webhook: %s", str(e))
        return HttpResponse(status=400, content="Webhook processing failed.".encode("utf-8"))

    logger.info("Received Stripe Connect event: %s", event.type)
    if event.type in ["payout.paid", "payout.failed", "payout.updated", "payout.canceled"]:
        payout_object = event.data.object

        logger.info(
            "Processing Stripe Connect payout webhook: %s for payout %s",
            event.type,
            getattr(payout_object, "id", "unknown"),
        )

        try:
            # Extract basic payout info for logging
            stripe_payout_id = getattr(payout_object, "id", None)
            payout_status = getattr(payout_object, "status", None)
            _payout_arrival_date = getattr(payout_object, "arrival_date", None)

            logger.debug(
                "Payout details (id=%s, status=%s)",
                stripe_payout_id,
                payout_status,
            )

            # Use transaction-wrapped function to handle payout updates
            # CRITICAL: Each webhook event processed with proper model ordering
            def process_webhook_event():
                """Process one payout webhook using READ COMMITTED and proper model ordering."""

                @retry_on_deadlock(max_retries=3, delay=0.01, backoff=2.0)  # 10ms initial delay
                def isolated_webhook_update():
                    """Run the payout update in a transaction with rollback safety and deadlock retry."""
                    with atomic_with_isolation("READ COMMITTED"):
                        with rollback_safe_operation("Payout Webhook Processing"):
                            return update_payout_from_webhook(event, payout_object)

                return isolated_webhook_update()

            try:
                updated_payout = process_webhook_event()
            except Exception as webhook_error:
                # Log webhook-specific error but don't break other events
                logger.error(f"[ERROR] Error processing {event.type} webhook: {webhook_error}")
                # Continue processing - each event is independent
                updated_payout = None

            if updated_payout:
                logger.info(f"[SUCCESS] Payout {updated_payout.id} processed successfully via transaction")
            else:
                logger.warning("[WARNING] Payout processing returned None - may not exist in database")

        except Exception as e:
            logger.error(f"[ERROR] Error processing {event.type} webhook: {e}")
            # Don't fail the webhook for payout processing errors
    else:
        logger.info("Unhandled Stripe Connect payout event type: %s", event.type)

    return HttpResponse(status=200, content=f"{event.type} connect webhook successfully processed".encode("utf-8"))


def get_product_image_url(product, request=None):
    """Return the best product image URL, preferring presigned S3 URLs then stored fields.

    Args:
        product: Product instance
        request: Optional request object to build absolute URIs for relative paths
    """
    if not product.images.exists():
        return ""

    primary_image = product.images.filter(is_primary=True).first()
    if not primary_image:
        primary_image = product.images.first()

    if not primary_image:
        return ""

    url = ""
    # Try to get presigned URL first (best option)
    try:
        presigned_url = primary_image.get_presigned_url(expires_in=3600)
        if presigned_url:
            print(f"🔗 Using presigned URL for product {product.name}: {presigned_url[:50]}...")
            url = presigned_url
    except Exception as e:
        print(f"⚠️ Failed to get presigned URL for product {product.name}: {str(e)}")

    # Fallback to image_url property if no presigned URL
    if not url:
        try:
            image_url = primary_image.image_url
            if image_url:
                print(f"🔗 Using image_url for product {product.name}: {image_url[:50]}...")
                url = image_url
        except Exception as e:
            print(f"⚠️ Failed to get image_url for product {product.name}: {str(e)}")

    # Final fallback to basic URL
    if not url:
        try:
            basic_url = primary_image.image.url
            print(f"🔗 Using basic image URL for product {product.name}: {basic_url[:50]}...")
            url = basic_url
        except Exception as e:
            print(f" Failed to get any image URL for product {product.name}: {str(e)}")
            return ""

    # Ensure absolute URI if request is provided and URL is relative
    if url and url.startswith("/") and request:
        return request.build_absolute_uri(url)

    return url


# Create a Stripe Embedded Checkout Session
@extend_schema(
    operation_id="payment_create_checkout",
    summary="Create Stripe Checkout Session",
    description="Creates an embedded checkout session for the user's cart.",
    responses={
        200: OpenApiResponse(response=CheckoutSessionResponseSerializer, description="Session created"),
        400: OpenApiResponse(response=ErrorResponseSerializer, description="Bad request"),
    },
    tags=["Payments"],
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@financial_transaction
def create_checkout_session(request):
    """Create an Embedded Checkout Session for the user's cart and seed the Order.

    This function validates stock and pricing, builds Stripe line items (products +
    shipping), creates an Order in pending_payment with reserved stock, starts an
    embedded checkout session carrying order/user metadata, and returns clientSecret.
    """
    print(f"DEBUG: create_checkout_session - User authenticated: {request.user.is_authenticated}")
    try:
        # Get the user's cart
        cart, _ = Cart.objects.get_or_create(user=request.user)
        cart_items = cart.items.all()

        if not cart_items.exists():
            return Response(
                {"error": "EMPTY_CART", "detail": "Your cart is empty"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Prepare line items for Stripe
        line_items = []
        for item in cart_items:
            if item.product.stock_quantity < item.quantity:
                return Response(
                    {"error": "INSUFFICIENT_STOCK", "detail": f"Insufficient stock for product {item.product.name}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # Prepare line item for each product in the cart
            if item.product.price <= 0:
                return Response(
                    {"error": "INVALID_PRICE", "detail": f"Invalid price for product {item.product.name}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if item.quantity <= 0:
                return Response(
                    {"error": "INVALID_QUANTITY", "detail": f"Invalid quantity for product {item.product.name}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # Add product line item
            line_items.append(
                {
                    "price_data": {
                        "currency": "usd",
                        "unit_amount": int(item.product.price * 100),  # Convert to cents
                        "product_data": {
                            "name": item.product.name,
                            "description": item.product.short_description or item.product.description[:100],
                            "images": (
                                [get_product_image_url(item.product, request)]
                                if get_product_image_url(item.product, request)
                                else []
                            ),
                        },
                    },
                    "quantity": item.quantity,
                }
            )

        # Add shipping line item
        line_items.append(
            {
                "price_data": {
                    "currency": "usd",
                    "unit_amount": 1999,  # $19.99 shipping
                    "product_data": {
                        "name": "Shipping",
                        "description": "Standard shipping",
                    },
                },
                "quantity": 1,
            }
        )

        # Create order with pending_payment status before Stripe session
        print(f"🔔 Creating order with pending_payment status for user {request.user.id}")

        with atomic_with_isolation("READ COMMITTED"):
            # Calculate totals from cart
            subtotal = sum(item.total_price for item in cart_items)
            shipping_cost = Decimal("19.99")  # Fixed shipping for now
            tax_amount = Decimal("0.00")  # Stripe will handle tax calculation
            total_amount = subtotal + shipping_cost + tax_amount  # Total will be re-calculated by Stripe

            # Create the order with pending_payment status
            order = Order.objects.create(
                buyer=request.user,
                status="pending_payment",  # Order starts as pending payment
                payment_status="pending",  # Payment status is pending
                subtotal=subtotal,
                shipping_cost=shipping_cost,
                tax_amount=tax_amount,  # Set to 0.00 as Stripe will handle
                total_amount=total_amount,  # Temporary, will be updated by webhook
                shipping_address={},  # Will be filled by Stripe checkout webhook
                is_locked=False,  # Order is not locked until payment succeeds
            )

            print(f"📦 Order {order.id} created with status 'pending_payment'")

            # Create order items from cart items
            for cart_item in cart_items:
                product = cart_item.product

                # Create order item
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    seller=product.seller,
                    quantity=cart_item.quantity,
                    unit_price=product.price,
                    total_price=cart_item.total_price,
                    product_name=product.name,
                    product_description=product.description,
                    product_image=get_product_image_url(product),
                )

                # Reserve stock (reduce stock quantity immediately)
                if product.stock_quantity >= cart_item.quantity:
                    product.stock_quantity -= cart_item.quantity
                    product.save(update_fields=["stock_quantity"])
                    print(f"📦 Reserved {cart_item.quantity} units of {product.name}")
                else:
                    print(f"⚠️ Warning: Insufficient stock for product {product.name}")
                    # In a production system, you might want to handle this differently

            print(f"  Order {order.id} created successfully with {cart_items.count()} items")

            # Clear cart after order creation
            cart.items.all().delete()
            print(f"🛒 Cart cleared for user {request.user.username}")

        print(f"🔔 Creating Stripe checkout session for order {order.id}")
        # Ensure FRONTEND_URL is valid for return_url
        frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173")
        if not frontend_url.startswith("http"):
            frontend_url = f"https://{frontend_url}"

        # Create Stripe Embedded Checkout Session with order_id instead of cart_id
        session_data = payment_provider.create_checkout_session(
            line_items=line_items,
            customer_email=request.user.email,
            mode="payment",
            success_url=f"{frontend_url}/checkout/confirmation/{order.id}",
            cancel_url=frontend_url,  # Fallback cancel URL
            metadata={
                "user_id": str(request.user.id),
                "order_id": str(order.id),
            },
            payment_intent_data={
                "transfer_group": f"ORDER{order.id}",
                "metadata": {
                    "user_id": str(request.user.id),
                    "order_id": str(order.id),
                },
            },
            automatic_tax={"enabled": True},
            locale=str(request.user.language) or "en",
            shipping_address_collection={
                "allowed_countries": ["US", "CA"]
            },  # Enable Stripe to collect shipping address
        )

        print(f"  Checkout session created: {session_data['sessionId']}")
        print(f"  Session client_secret: {session_data['clientSecret'][:20]}...")

        # PaymentTracker will be created in checkout session complete webhook
        # when we have the actual payment_intent ID
        logger.info(f"Checkout session {session_data['sessionId']} created for order {order.id}")
        print("📊 Checkout session created - PaymentTracker will be created on completion")

        return JsonResponse({"clientSecret": session_data["clientSecret"]})

    except Exception as e:
        logger.error(f"Error creating checkout session: {str(e)}")
        return Response(
            {"error": "CHECKOUT_SESSION_CREATION_FAILED", "detail": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@extend_schema(
    operation_id="payment_retry_checkout",
    summary="Retry Failed Checkout",
    description="Creates a retry session for a pending order.",
    responses={
        200: OpenApiResponse(response=CheckoutSessionResponseSerializer, description="Retry session created"),
        400: OpenApiResponse(response=ErrorResponseSerializer, description="Invalid order state"),
        404: OpenApiResponse(response=ErrorResponseSerializer, description="Order not found"),
    },
    tags=["Payments"],
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def create_checkout_failed_checkout(request, order_id):
    """Create a retry Embedded Checkout Session for a pending order.

    This function verifies ownership and 'pending_payment' status, rebuilds Stripe line
    items from the order (with stock checks), creates an embedded checkout session with
    order/user metadata, and returns the clientSecret for the frontend to resume.
    """
    if request.method != "GET":
        return Response(
            {"error": "METHOD_NOT_ALLOWED", "detail": "This endpoint only supports GET requests"},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    order = Order.objects.filter(id=order_id, buyer=request.user).first()
    if order is None:
        return Response({"error": "ORDER_NOT_FOUND", "detail": "Order not found"}, status=status.HTTP_404_NOT_FOUND)
    if order.status != "pending_payment":
        return Response(
            {"error": "ORDER_NOT_PENDING", "detail": "Order is not in pending payment status"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    # If the order is found and in pending payment status, redirect to the checkout page

    try:
        # Get the user's order items
        order_items = order.items.all()
        if not order_items.exists():
            return Response(
                {"error": "EMPTY_ORDER", "detail": "Your order is empty"}, status=status.HTTP_400_BAD_REQUEST
            )
        # Prepare line items for Stripe
        line_items = []
        for item in order_items:
            if item.product.stock_quantity < item.quantity:
                return Response(
                    {"error": "INSUFFICIENT_STOCK", "detail": f"Insufficient stock for product {item.product.name}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # Prepare line item for each product in the order
            if item.product.price <= 0:
                return Response(
                    {"error": "INVALID_PRICE", "detail": f"Invalid price for product {item.product.name}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if item.quantity <= 0:
                return Response(
                    {"error": "INVALID_QUANTITY", "detail": f"Invalid quantity for product {item.product.name}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # Add product line item
            line_items.append(
                {
                    "price_data": {
                        "currency": "usd",
                        "unit_amount": int(item.product.price * 100),  # Convert to cents
                        "product_data": {
                            "name": item.product.name,
                            "description": item.product.short_description or item.product.description[:100],
                            "images": (
                                [get_product_image_url(item.product, request)]
                                if get_product_image_url(item.product, request)
                                else []
                            ),
                        },
                    },
                    "quantity": item.quantity,
                }
            )
        # Add shipping line item
        line_items.append(
            {
                "price_data": {
                    "currency": "usd",
                    "unit_amount": 1999,  # $19.99 shipping
                    "product_data": {
                        "name": "Shipping",
                        "description": "Standard shipping",
                    },
                },
                "quantity": 1,
            }
        )

        # Ensure FRONTEND_URL is valid for return_url
        frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173")
        if not frontend_url.startswith("http"):
            frontend_url = f"https://{frontend_url}"

        print(f"🔔 Creating Stripe checkout session for order {order.id}")
        # Create Stripe Embedded Checkout Session with order_id instead of cart_id
        session_data = payment_provider.create_checkout_session(
            line_items=line_items,
            customer_email=request.user.email,
            mode="payment",
            success_url=f"{frontend_url}/checkout/confirmation/{order.id}",
            cancel_url=frontend_url,  # Fallback cancel URL
            metadata={
                "user_id": str(request.user.id),
                "order_id": str(order.id),
            },
            payment_intent_data={
                "transfer_group": f"ORDER{order.id}",
                "metadata": {
                    "user_id": str(request.user.id),
                    "order_id": str(order.id),
                },
            },
            automatic_tax={"enabled": True},
            locale=str(request.user.language) or "en",
            shipping_address_collection={
                "allowed_countries": ["US", "CA"]
            },  # Enable Stripe to collect shipping address
        )

        print(f"  Checkout session created: {session_data['sessionId']}")
        print(f"  Session client_secret: {session_data['clientSecret'][:20]}...")

        # PaymentTracker will be created in checkout session complete webhook
        # when we have the actual payment_intent ID
        logger.info(f"Retry checkout session {session_data['sessionId']} created for order {order.id}")
        print("📊 Retry checkout session created - PaymentTracker will be created on completion")

        return JsonResponse({"clientSecret": session_data["clientSecret"]})

    except Exception as e:
        logger.error(f"Error creating checkout session: {str(e)}")
        return Response(
            {"error": "CHECKOUT_SESSION_CREATION_FAILED", "detail": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# Cancel an order and process Stripe refund if payment was made
@extend_schema(
    operation_id="payment_cancel_order",
    summary="Cancel Order",
    description="Cancels an order and initiates refund if paid.",
    request=OrderCancellationRequestSerializer,
    responses={
        200: OpenApiResponse(response=OrderCancellationResponseSerializer, description="Order cancelled"),
        400: OpenApiResponse(response=ErrorResponseSerializer, description="Cannot cancel"),
        403: OpenApiResponse(response=ErrorResponseSerializer, description="Permission denied"),
        404: OpenApiResponse(response=ErrorResponseSerializer, description="Order not found"),
    },
    tags=["Payments"],
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cancel_order(request, order_id):  # noqa: C901
    """Cancel an order with refund handling and stock restoration.

    This function cancels orders that are 'pending_payment' by restoring reserved stock,
    marking cancellation metadata, and setting payment_status to 'failed'. If the order
    was paid, it initiates a Stripe refund, moves the order to 'waiting_refund', and
    persists metadata; final status transitions occur via the refund webhook. Terminal
    states (shipped, delivered, cancelled, refunded) are rejected.
    """
    try:
        with atomic_with_isolation("READ COMMITTED"):
            # Get the order
            try:
                order = Order.objects.get(id=order_id)
            except Order.DoesNotExist:
                return Response(
                    {"error": "ORDER_NOT_FOUND", "detail": "Order not found"}, status=status.HTTP_404_NOT_FOUND
                )

            # Verify user permissions
            user_owns_items = order.items.filter(seller=request.user).exists()
            is_buyer = order.buyer == request.user
            is_staff = request.user.is_staff

            if not (user_owns_items or is_buyer or is_staff):
                return Response(
                    {
                        "error": "PERMISSION_DENIED",
                        "detail": "You must be the seller of at least one item or the buyer to cancel this order",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            # Check if order can be cancelled
            if order.status in ["shipped", "delivered", "cancelled", "refunded"]:
                return Response(
                    {
                        "error": "CANNOT_CANCEL",
                        "detail": f"Order cannot be cancelled. Current status: {order.status}. Orders can only be cancelled before shipping.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Fast-path: pending payment orders are cancelled immediately and stock is restored
            if order.status == "pending_payment":
                # Persist cancellation metadata
                order.cancellation_reason = request.data.get("cancellation_reason", "")
                order.cancelled_by = request.user
                order.cancelled_at = timezone.now()

                # Restore previously reserved stock
                try:
                    for item in order.items.all():
                        product = item.product
                        if product:
                            product.stock_quantity += item.quantity
                            product.save(update_fields=["stock_quantity"])
                except Exception as stock_err:
                    logger.error(f"Error restoring stock for order {order.id}: {stock_err}")

                # Cancel order and set payment status
                order.status = "cancelled"
                order.payment_status = "failed"
                order.save(
                    update_fields=["status", "payment_status", "cancellation_reason", "cancelled_by", "cancelled_at"]
                )

                return Response(
                    {
                        "success": True,
                        "message": "Order cancelled successfully.",
                        "refund_requested": False,
                        "refund_amount": None,
                        "stripe_refund_id": None,
                        "order": {
                            "id": str(order.id),
                            "status": order.status,
                            "payment_status": order.payment_status,
                            "cancelled_at": order.cancelled_at.isoformat() if order.cancelled_at else None,
                            "cancellation_reason": order.cancellation_reason,
                            "cancelled_by": (
                                {"id": order.cancelled_by.id, "username": order.cancelled_by.username}
                                if order.cancelled_by
                                else None
                            ),
                        },
                    },
                    status=status.HTTP_200_OK,
                )

            # Get cancellation reason from request
            cancellation_reason = request.data.get("cancellation_reason", "")
            if not cancellation_reason:
                return Response(
                    {"error": "MISSING_REASON", "detail": "Cancellation reason is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Check if payment needs to be refunded
            refund_processed = False
            refund_amount = Decimal("0.00")
            stripe_refund_id = None

            # Only process refund if payment was completed
            if order.payment_status == "paid":
                try:
                    # Try to find payment tracker in our system first
                    payment_tracker = PaymentTracker.objects.filter(
                        order=order, transaction_type="payment", status="succeeded"
                    ).first()

                    # If we have a payment tracker, use it for refund
                    if payment_tracker and payment_tracker.stripe_payment_intent_id:
                        refund_amount = payment_tracker.amount

                        # Create refund through Stripe
                        stripe_refund = payment_provider.create_refund(
                            payment_intent_id=payment_tracker.stripe_payment_intent_id,
                            amount=int(refund_amount * 100),  # Convert to cents
                            reason="requested_by_customer",
                            metadata={
                                "order_id": str(order.id),
                                "cancelled_by": str(request.user.id),
                                "reason": cancellation_reason,
                            },
                        )

                        stripe_refund_id = stripe_refund.id

                        # Create refund tracker
                        try:
                            PaymentTracker.objects.create(
                                stripe_refund_id=stripe_refund_id,
                                order=order,
                                user=request.user,
                                transaction_type="refund",
                                status="succeeded",
                                amount=refund_amount,
                                currency="USD",
                                notes=f"Order cancelled: {cancellation_reason}",
                            )
                            logger.info(f"Created refund tracker for order {order.id}, refund {stripe_refund_id}")
                            print(f"  Created refund tracker for order {order.id}")
                        except Exception as tracker_error:
                            logger.error(f"Failed to create refund tracker: {str(tracker_error)}")
                            print(f"⚠️ Failed to create refund tracker: {str(tracker_error)}")
                            # Don't fail the refund processing if tracker creation fails

                        payment_transactions = PaymentTransaction.objects.filter(
                            order=order,
                            status="held",  # Only refund held transactions
                        )

                        for transaction in payment_transactions:
                            transaction.status = "waiting_refund"
                            # Add refund information to existing notes field
                            refund_note = f"Refund initiated due to order cancellation: {cancellation_reason} (Amount: ${refund_amount})"
                            transaction.notes = (
                                f"{transaction.notes}\n{refund_note}" if transaction.notes else refund_note
                            )
                            transaction.save(update_fields=["status", "notes"])

                        # Update order status to waiting_refund initially
                        order.status = "waiting_refund"
                        order.save(update_fields=["status"])
                        print(f"  Order {order.id} status set to 'waiting_refund'")

                        refund_processed = True
                        logger.info(f"Stripe refund processed: {stripe_refund_id} for order {order.id}")

                except ConnectionError as stripe_error:
                    logger.error(f"Stripe refund failed: {str(stripe_error)}")
                    return Response(
                        {
                            "error": "REFUND_FAILED",
                            "detail": f"Failed to process refund: {str(stripe_error)}",
                            "stripe_error": str(stripe_error),
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                except Exception as refund_error:
                    logger.error(f"Refund processing failed: {str(refund_error)}")
                    return Response(
                        {"error": "REFUND_ERROR", "detail": f"Error processing refund: {str(refund_error)}"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )

            # Store cancellation request data but don't update order status yet
            # Order status will be updated by webhook when refund is confirmed
            order.cancellation_reason = cancellation_reason
            order.cancelled_by = request.user
            order.cancelled_at = timezone.now()
            order.save(update_fields=["cancellation_reason", "cancelled_by", "cancelled_at"])

            # Log the cancellation request
            logger.info(
                f"Cancellation requested for order {order.id} by user {request.user.username}. Refund initiated: {refund_processed}"
            )

            return Response(
                {
                    "success": True,
                    "message": (
                        "Cancellation request submitted. Order status will be updated when refund is processed."
                        if refund_processed
                        else "Order cancelled successfully."
                    ),
                    "refund_requested": refund_processed,
                    "refund_amount": str(refund_amount) if refund_processed else None,
                    "stripe_refund_id": stripe_refund_id,
                    "order": {
                        "id": str(order.id),
                        "status": order.status,  # Keep current status
                        "payment_status": order.payment_status,  # Keep current payment status
                        "cancelled_at": order.cancelled_at.isoformat() if order.cancelled_at else None,
                        "cancellation_reason": order.cancellation_reason,
                        "cancelled_by": (
                            {"id": order.cancelled_by.id, "username": order.cancelled_by.username}
                            if order.cancelled_by
                            else None
                        ),
                    },
                },
                status=status.HTTP_200_OK,
            )

    except Exception as e:
        logger.error(f"Error cancelling order {order_id}: {str(e)}")
        return Response(
            {"error": "ORDER_CANCELLATION_FAILED", "detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# Stripe Connect Views for Seller Account Management

from payment_system.domain.services.stripe_service import StripeConnectService  # noqa: E402


@extend_schema(
    methods=["GET"],
    operation_id="payment_stripe_account_status",
    summary="Get Stripe Account Status",
    description="Check status of the connected Stripe account.",
    responses={
        200: OpenApiResponse(response=StripeAccountStatusResponseSerializer, description="Account status"),
        400: OpenApiResponse(response=ErrorResponseSerializer, description="Error"),
    },
    tags=["Stripe Connect"],
)
@extend_schema(
    methods=["POST"],
    operation_id="payment_create_stripe_account",
    summary="Create Stripe Account",
    description="Create a new Stripe Connect account.",
    request=StripeAccountCreateRequestSerializer,
    responses={
        201: OpenApiResponse(response=StripeAccountStatusResponseSerializer, description="Account created"),
        400: OpenApiResponse(response=ErrorResponseSerializer, description="Bad request"),
    },
    tags=["Stripe Connect"],
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@financial_transaction
def stripe_account(request):  # noqa: C901
    """Unified endpoint for Stripe Connect account management.

    This function returns existing account status on GET, or creates a new account on
    POST after basic eligibility checks, surfacing requirements and next steps for the
    seller’s onboarding.
    """
    try:
        user = request.user

        if request.method == "GET":
            print(f"🔍 GET /stripe/account for user: {user.email}")

            # Check if user already has a Stripe account
            if user.stripe_account_id:
                print(f"  User has existing account: {user.stripe_account_id}")

                # Get account status using the service
                result = StripeConnectService.get_account_status(user)

                if result["success"]:
                    return Response(
                        {
                            "has_account": True,
                            "account_id": result["account_id"],
                            "status": result["status"],
                            "details_submitted": result["details_submitted"],
                            "charges_enabled": result["charges_enabled"],
                            "payouts_enabled": result["payouts_enabled"],
                            "requirements": result["requirements"],
                            "message": "Account exists and details retrieved successfully.",
                        },
                        status=status.HTTP_200_OK,
                    )
                else:
                    return Response(
                        {"error": "Failed to get account status.", "details": result["errors"]},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            else:
                print("ℹ️ User doesn't have account, checking eligibility...")

                # Check eligibility for account creation
                validation = StripeConnectService.validate_seller_requirements(user)

                return Response(
                    {
                        "has_account": False,
                        "eligible_for_creation": validation["valid"],
                        "eligibility_errors": validation["errors"],
                        "requirements": {
                            "is_authenticated": True,
                            "is_oauth_user": user.is_oauth_only_user(),
                            "has_password": user.has_usable_password(),
                            "two_factor_enabled": getattr(user, "two_factor_enabled", False),
                        },
                        "message": "No account exists. Check eligibility for creation.",
                    },
                    status=status.HTTP_200_OK,
                )

        elif request.method == "POST":
            print(f"🔄 POST /stripe/account for user: {user.email}")

            # Check if user already has account
            if user.stripe_account_id:
                print(f"ℹ️ User already has account: {user.stripe_account_id}, returning account info")

                # Return existing account info instead of creating new one
                result = StripeConnectService.get_account_status(user)

                if result["success"]:
                    return Response(
                        {
                            "account_exists": True,
                            "account_id": result["account_id"],
                            "status": result["status"],
                            "details_submitted": result["details_submitted"],
                            "charges_enabled": result["charges_enabled"],
                            "payouts_enabled": result["payouts_enabled"],
                            "requirements": result["requirements"],
                            "message": "Account already exists. Returning existing account information.",
                        },
                        status=status.HTTP_200_OK,
                    )
                else:
                    return Response(
                        {"error": "Failed to get existing account status.", "details": result["errors"]},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            else:
                print("🚀 Creating new Stripe account...")

                # Get optional parameters for account creation
                country = request.data.get("country", "US")
                business_type = request.data.get("business_type", "individual")

                # Validate country code
                if len(country) != 2:
                    return Response(
                        {"error": "Invalid country code. Please provide a 2-letter ISO country code."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # Validate business type
                if business_type not in ["individual", "company"]:
                    return Response(
                        {"error": 'Invalid business type. Must be "individual" or "company".'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # Create Stripe account using the service
                result = StripeConnectService.create_stripe_account(user, country, business_type)

                if result["success"]:
                    return Response(
                        {
                            "account_created": True,
                            "account_id": result["account_id"],
                            "status": "incomplete",  # New accounts are always incomplete
                            "message": "Stripe account created successfully.",
                            "next_step": "Complete account setup using the account session.",
                        },
                        status=status.HTTP_201_CREATED,
                    )
                else:
                    return Response(
                        {"error": "Failed to create Stripe account.", "details": result["errors"]},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

    except Exception as e:
        logger.error(f"Unexpected error in stripe_account: {str(e)}")
        return Response(
            {"error": "Service may be unavailable. Please try again later."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# This creates a Stripe Account Session for seller onboarding AKA get seller info to pay or edit the info
@extend_schema(
    operation_id="payment_create_account_session",
    summary="Create Account Session",
    description="Creates a session for Stripe Connect onboarding.",
    responses={
        200: OpenApiResponse(response=StripeAccountSessionResponseSerializer, description="Session created"),
        400: OpenApiResponse(response=ErrorResponseSerializer, description="Failed to create session"),
    },
    tags=["Stripe Connect"],
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_stripe_account_session(request):
    """Create a Stripe Account Session for seller onboarding or updates.

    This function returns an Account Session client_secret for onboarding or updating a
    seller’s connected account. Requires the user to have an existing Stripe account.
    """
    try:
        user = request.user

        # Create account session using the service
        result = StripeConnectService.create_account_session(user)

        if result["success"]:
            return Response(
                {
                    "message": "Account session created successfully.",
                    "client_secret": result["client_secret"],
                    "account_id": result["account_id"],
                },
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"error": "Failed to create account session.", "details": result["errors"]},
                status=status.HTTP_400_BAD_REQUEST,
            )

    except Exception as e:
        logger.error(f"Unexpected error in create_stripe_account_session: {str(e)}")
        return Response(
            {"error": "Service may be unavailable. Please try again later."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# Get the Stripe account status for the authenticated user
@extend_schema(
    operation_id="payment_get_account_status",
    summary="Get Stripe Account Status",
    description="Returns status of the connected Stripe account.",
    responses={
        200: OpenApiResponse(response=StripeAccountStatusResponseSerializer, description="Account status"),
        400: OpenApiResponse(response=ErrorResponseSerializer, description="Error"),
    },
    tags=["Stripe Connect"],
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_stripe_account_status(request):
    """Return the Stripe Connect account status for the authenticated user."""
    try:
        user = request.user

        # Get account status using the service
        result = StripeConnectService.get_account_status(user)

        if result["success"]:
            response_data = {"has_stripe_account": result["has_account"]}

            # Add detailed information if account exists
            if result["has_account"]:
                response_data.update(
                    {
                        "details_submitted": result["details_submitted"],
                        "charges_enabled": result["charges_enabled"],
                        "payouts_enabled": result["payouts_enabled"],
                        "requirements": result["requirements"],
                    }
                )

            return Response(response_data, status=status.HTTP_200_OK)
        else:
            return Response(
                {"error": "Failed to get account status.", "details": result["errors"]},
                status=status.HTTP_400_BAD_REQUEST,
            )

    except Exception as e:
        logger.error(f"Unexpected error in get_stripe_account_status: {str(e)}")
        return Response(
            {"error": "Service may be unavailable. Please try again later."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def create_transfer_to_connected_account(amount, currency, destination_account_id, transfer_group=None, metadata=None):
    """Helper function to create a Stripe transfer to a connected account.

    Wraps payment_provider.create_transfer() and returns a standardized response format.

    Args:
        amount (int): Transfer amount in cents
        currency (str): Currency code (e.g., 'usd')
        destination_account_id (str): Stripe connected account ID
        transfer_group (str, optional): Transfer group ID for grouping related transfers
        metadata (dict, optional): Additional metadata to attach to the transfer

    Returns:
        dict: Standardized transfer result with success status and transfer details
    """
    try:
        # Build metadata for the transfer
        transfer_metadata = metadata or {}
        if transfer_group:
            transfer_metadata["transfer_group"] = transfer_group

        # Create the transfer using the payment provider
        transfer_id = payment_provider.create_transfer(
            destination_id=destination_account_id, amount=amount, currency=currency, metadata=transfer_metadata
        )

        logger.info(f"Transfer created successfully: {transfer_id}")

        return {
            "success": True,
            "transfer_id": transfer_id,
            "amount": amount,
            "currency": currency,
            "destination": destination_account_id,
            "transfer_group": transfer_group,
            "created": timezone.now().isoformat(),
            "errors": [],
        }

    except (ConnectionError, RuntimeError) as e:
        logger.error(f"Failed to create transfer: {str(e)}")
        return {"success": False, "transfer_id": None, "errors": [str(e)]}
    except Exception as e:
        logger.error(f"Unexpected error creating transfer: {str(e)}", exc_info=True)
        return {"success": False, "transfer_id": None, "errors": [f"Unexpected error: {str(e)}"]}


# transfer payment to seller's connected account
@extend_schema(
    operation_id="payment_transfer_to_seller",
    summary="Transfer Payment",
    description="Transfers held funds to the seller's connected account.",
    request=TransferRequestSerializer,
    responses={
        200: OpenApiResponse(response=TransferResponseSerializer, description="Transfer successful"),
        400: OpenApiResponse(response=ErrorResponseSerializer, description="Transfer failed"),
        403: OpenApiResponse(response=ErrorResponseSerializer, description="Permission denied"),
        404: OpenApiResponse(response=ErrorResponseSerializer, description="Transaction not found"),
    },
    tags=["Stripe Connect"],
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@financial_transaction
def transfer_payment_to_seller(request):  # noqa: C901
    """Transfer held funds to a seller’s connected Stripe account.

    This function validates permissions and readiness (held status, delivered order,
    optional release date), computes the transfer amount in cents, and creates a Stripe
    transfer, returning details along with exchange-rate context.
    """
    try:
        # Get request data
        transaction_id = request.data.get("transaction_id")
        transfer_group = request.data.get("transfer_group")

        if not transaction_id:
            return Response(
                {"error": "MISSING_TRANSACTION_ID", "detail": "Transaction ID is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get the payment transaction
        try:
            payment_transaction = PaymentTransaction.objects.select_related("seller", "buyer", "order").get(
                id=transaction_id
            )
        except PaymentTransaction.DoesNotExist:
            return Response(
                {"error": "TRANSACTION_NOT_FOUND", "detail": f"Payment transaction {transaction_id} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Security check: Only allow admins or the seller to trigger transfer
        if not (request.user.is_staff or request.user == payment_transaction.seller):
            return Response(
                {"error": "PERMISSION_DENIED", "detail": "You do not have permission to transfer this payment"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # SECURITY: Only allow transfers of payments with 'held' status
        if not payment_transaction.can_transfer:
            return Response(
                {
                    "error": "PAYMENT_NOT_TRANSFERABLE",
                    "detail": f'Only payments with "held" status can be transferred. Current status: {payment_transaction.status}',
                    "payment_status": payment_transaction.status,
                    "transfer_allowed": False,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if seller has a connected Stripe account
        if not payment_transaction.seller.stripe_account_id:
            return Response(
                {"error": "NO_CONNECTED_ACCOUNT", "detail": "Seller does not have a connected Stripe account"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if payment_transaction.planned_release_date and payment_transaction.planned_release_date > timezone.now():
            return Response(
                {
                    "error": "TRANSFER_NOT_READY",
                    "detail": f"Transfer not ready yet. Planned release date: {payment_transaction.planned_release_date.isoformat()}",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if payment_transaction.status != "held":
            return Response(
                {
                    "error": "INVALID_PAYMENT_STATUS",
                    "detail": f'Payment transaction must be in "held" status to transfer. Current status: {payment_transaction.status}',
                    "payment_status": payment_transaction.status,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if payment_transaction.order.status not in ["delivered"]:
            return Response(
                {
                    "error": "INVALID_ORDER_STATUS",
                    "detail": f'Order must be in "delivered" status to transfer payment. Current status: {payment_transaction.order.status}',
                    "order_status": payment_transaction.order.status,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Use transfer group from request or default to order ID
        if not transfer_group:
            transfer_group = f"ORDER{payment_transaction.order.id}"

        # Calculate transfer amount in cents
        transfer_amount_cents = int(payment_transaction.net_amount * 100)

        # Use currency handler to check balance and find optimal currency
        from payment_system.domain.services.currency_handler import CurrencyHandler, switch_currency

        # Get current balance information for enhanced response
        try:
            current_balance = CurrencyHandler.get_available_currencies_with_balance()
            logger.info(f"Current balance available: {len(current_balance)} currencies")
        except Exception as balance_error:
            logger.warning(f"Could not retrieve balance info: {balance_error}")
            current_balance = []

        # Check exchange rate data freshness
        try:
            rate_freshness = CurrencyHandler.check_exchange_rate_freshness()
            if not rate_freshness["is_fresh"]:
                logger.warning(
                    f"Exchange rate data is stale (age: {rate_freshness.get('age_hours', 'unknown')} hours)"
                )
        except Exception as freshness_error:
            logger.warning(f"Could not check exchange rate freshness: {freshness_error}")
            rate_freshness = {"is_fresh": False, "status": "unknown"}

        currency_result = switch_currency(
            preferred_currency=payment_transaction.currency.lower(),
            required_amount_cents=transfer_amount_cents,
            destination_account_id=payment_transaction.seller.stripe_account_id,
        )

        # Handle currency response format
        if "success" in currency_result and "was_converted" in currency_result:
            if currency_result["was_converted"]:
                # Currency conversion was needed
                logger.info(
                    f"Currency conversion applied: {currency_result['original_currency']} to {currency_result['new_currency'].upper()} (rate: {currency_result['rate']})"
                )

                # Create transfer with converted currency and amount
                transfer_result = create_transfer_to_connected_account(
                    amount=currency_result["new_amount_cents"],  # Already in cents
                    currency=currency_result["new_currency"],
                    destination_account_id=payment_transaction.seller.stripe_account_id,
                    transfer_group=transfer_group,
                    metadata={
                        "transaction_id": str(payment_transaction.id),
                        "order_id": str(payment_transaction.order.id),
                        "seller_id": str(payment_transaction.seller.id),
                        "buyer_id": str(payment_transaction.buyer.id),
                        "original_currency": currency_result["original_currency"],
                        "original_amount_cents": currency_result["original_amount_cents"],
                        "currency_conversion": True,
                        "exchange_rate": currency_result["rate"],
                    },
                )
            else:
                # No conversion needed - use original values
                logger.info(
                    f"No currency conversion needed: using {currency_result.get('use_currency_display', payment_transaction.currency.upper())}"
                )

                # Create transfer with original currency and amount
                transfer_result = create_transfer_to_connected_account(
                    amount=currency_result.get("amount_cents", transfer_amount_cents),
                    currency=currency_result.get("use_currency", payment_transaction.currency.lower()),
                    destination_account_id=payment_transaction.seller.stripe_account_id,
                    transfer_group=transfer_group,
                    metadata={
                        "transaction_id": str(payment_transaction.id),
                        "order_id": str(payment_transaction.order.id),
                        "seller_id": str(payment_transaction.seller.id),
                        "buyer_id": str(payment_transaction.buyer.id),
                        "original_currency": payment_transaction.currency.upper(),
                        "original_amount_cents": transfer_amount_cents,
                        "currency_conversion": False,
                        "exchange_rate": 1.0,
                    },
                )

        elif "success" in currency_result:
            # Full response format - handle as before
            if not currency_result["success"]:
                logger.error(
                    f"Currency switch failed for transaction {transaction_id}: {currency_result.get('error')}"
                )

                # Check if it's an exchange rate error
                if currency_result.get("error_type") == "EXCHANGE_RATE_UNAVAILABLE":
                    return Response(
                        {
                            "error": "EXCHANGE_RATE_UNAVAILABLE",
                            "detail": currency_result.get("error"),
                            "message": currency_result.get("message"),
                            "exchange_rate_status": rate_freshness,
                            "required_action": "Update exchange rate data or contact system administrator",
                        },
                        status=status.HTTP_503_SERVICE_UNAVAILABLE,
                    )
                else:
                    # Handle other currency errors (insufficient balance, etc.)
                    return Response(
                        {
                            "error": "INSUFFICIENT_BALANCE",
                            "detail": f"Insufficient balance for transfer: {currency_result.get('error')}",
                            "balance_info": currency_result.get("balance_info", {}),
                            "available_currencies": currency_result.get("available_currencies", current_balance),
                            "current_balance_summary": {
                                "total_currencies_available": len(current_balance),
                                "highest_balance_currency": (
                                    current_balance[0]["currency"] if current_balance else None
                                ),
                                "currencies_with_balance": [
                                    {"currency": curr["currency"], "amount_formatted": curr["amount_formatted"]}
                                    for curr in current_balance[:5]  # Top 5 currencies
                                ],
                            },
                            "exchange_rate_status": rate_freshness,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        else:
            # Unknown response format
            logger.error(f"Unknown currency_result format for transaction {transaction_id}: {currency_result}")
            return Response(
                {
                    "error": "CURRENCY_HANDLER_ERROR",
                    "detail": "Unknown response format from currency handler",
                    "currency_result": currency_result,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if not transfer_result["success"]:
            logger.error(f"Failed to create transfer for transaction {transaction_id}: {transfer_result['errors']}")
            return Response(
                {
                    "error": "TRANSFER_FAILED",
                    "detail": "Failed to create transfer to seller account",
                    "errors": transfer_result["errors"],
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Update payment transaction status to 'processing' and store transfer_id
        transfer_started = payment_transaction.start_transfer(
            transfer_id=transfer_result["transfer_id"],
            notes=f"Transfer created by {request.user.username}: {transfer_result['transfer_id']}",
        )

        if not transfer_started:
            logger.error(f"Failed to update payment transaction status for {transaction_id}")
            return Response(
                {
                    "error": "STATUS_UPDATE_FAILED",
                    "detail": "Transfer created but failed to update transaction status",
                    "transfer_id": transfer_result["transfer_id"],
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        logger.info(
            f"Payment transferred successfully: Transaction {transaction_id}, Transfer {transfer_result['transfer_id']}"
        )

        # Get updated balance information after transfer
        try:
            post_transfer_balance = CurrencyHandler.get_available_currencies_with_balance()
        except Exception as balance_error:
            logger.warning(f"Could not retrieve post-transfer balance: {balance_error}")
            post_transfer_balance = current_balance

        # Build complete response based on currency result format
        if currency_result.get("was_converted"):
            # Currency conversion was performed
            logger.info("Building response for currency conversion scenario")

            response_data = {
                "success": True,
                "message": "Transfer initiated successfully with currency conversion. Status set to processing - awaiting webhook verification.",
                "transfer_details": {
                    "transfer_id": transfer_result["transfer_id"],
                    "amount_cents": transfer_result["amount"],
                    "amount_dollars": transfer_result["amount"] / 100,
                    "currency": transfer_result["currency"],
                    "destination_account": transfer_result["destination"],
                    "transfer_group": transfer_result["transfer_group"],
                    "created_at": transfer_result["created"],
                },
                "currency_info": {
                    "original_currency": currency_result["original_currency"],
                    "final_currency": currency_result["new_currency"].upper(),
                    "conversion_needed": True,
                    "exchange_rate": currency_result["rate"],
                    "original_amount_cents": currency_result["original_amount_cents"],
                    "original_amount_decimal": float(currency_result["original_amount_decimal"]),
                    "final_amount_cents": currency_result["new_amount_cents"],
                    "final_amount_decimal": float(currency_result["new_amount_decimal"]),
                    "conversion_summary": f"Converted {currency_result['original_amount_decimal']} {currency_result['original_currency']} to {currency_result['new_amount_decimal']} {currency_result['new_currency'].upper()} at rate {currency_result['rate']}",
                    "balance_used": {
                        "currency": currency_result["new_currency"].upper(),
                        "amount_used_cents": currency_result["new_amount_cents"],
                        "amount_used_decimal": float(currency_result["new_amount_decimal"]),
                    },
                },
                "transaction_details": {
                    "transaction_id": str(payment_transaction.id),
                    "status": payment_transaction.status,
                    "net_amount": float(payment_transaction.net_amount),
                    "release_date": (
                        payment_transaction.actual_release_date.isoformat()
                        if payment_transaction.actual_release_date
                        else None
                    ),
                },
                "balance_summary": {
                    "currencies_available_before": len(current_balance),
                    "currencies_available_after": len(post_transfer_balance),
                    "top_currencies_remaining": [
                        {
                            "currency": curr["currency"],
                            "amount_formatted": curr["amount_formatted"],
                            "amount_cents": curr["amount_cents"],
                        }
                        for curr in post_transfer_balance[:3]
                    ],
                    "transfer_impact": {
                        "currency_used": currency_result["new_currency"].upper(),
                        "amount_deducted": f"{currency_result['new_amount_decimal']:.2f} {currency_result['new_currency'].upper()}",
                    },
                },
                "exchange_rate_info": {
                    "data_freshness": rate_freshness,
                    "rate_source": "database_stored",
                    "conversion_rate": currency_result["rate"],
                    "rate_timestamp": rate_freshness.get("last_updated"),
                },
            }
        else:
            # No currency conversion needed
            logger.info("Building response for no conversion scenario")

            response_data = {
                "success": True,
                "message": "Transfer initiated successfully. Status set to processing - awaiting webhook verification.",
                "transfer_details": {
                    "transfer_id": transfer_result["transfer_id"],
                    "amount_cents": transfer_result["amount"],
                    "amount_dollars": transfer_result["amount"] / 100,
                    "currency": transfer_result["currency"],
                    "destination_account": transfer_result["destination"],
                    "transfer_group": transfer_result["transfer_group"],
                    "created_at": transfer_result["created"],
                },
                "currency_info": {
                    "original_currency": payment_transaction.currency.upper(),
                    "final_currency": currency_result.get(
                        "use_currency_display", payment_transaction.currency.upper()
                    ),
                    "conversion_needed": False,
                    "exchange_rate": 1.0,
                    "original_amount_cents": transfer_amount_cents,
                    "original_amount_decimal": float(payment_transaction.net_amount),
                    "final_amount_cents": transfer_amount_cents,
                    "final_amount_decimal": float(payment_transaction.net_amount),
                    "recommendation": currency_result.get("recommendation", "No conversion needed"),
                    "balance_used": {
                        "currency": currency_result.get("use_currency_display", payment_transaction.currency.upper()),
                        "amount_used_cents": transfer_amount_cents,
                        "amount_used_decimal": float(payment_transaction.net_amount),
                    },
                },
                "transaction_details": {
                    "transaction_id": str(payment_transaction.id),
                    "status": payment_transaction.status,
                    "net_amount": float(payment_transaction.net_amount),
                    "release_date": (
                        payment_transaction.actual_release_date.isoformat()
                        if payment_transaction.actual_release_date
                        else None
                    ),
                },
                "balance_summary": {
                    "currencies_available_before": len(current_balance),
                    "currencies_available_after": len(post_transfer_balance),
                    "top_currencies_remaining": [
                        {
                            "currency": curr["currency"],
                            "amount_formatted": curr["amount_formatted"],
                            "amount_cents": curr["amount_cents"],
                        }
                        for curr in post_transfer_balance[:3]
                    ],
                    "transfer_impact": {
                        "currency_used": currency_result.get(
                            "use_currency_display", payment_transaction.currency.upper()
                        ),
                        "amount_deducted": f"{payment_transaction.net_amount:.2f} {currency_result.get('use_currency_display', payment_transaction.currency.upper())}",
                    },
                },
                "exchange_rate_info": {
                    "data_freshness": rate_freshness,
                    "rate_source": "database_stored",
                    "fallback_used": currency_result.get("fallback_rates_used", False),
                },
            }

        return Response(response_data, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Unexpected error in transfer_payment_to_seller: {str(e)}", exc_info=True)
        return Response(
            {"error": "TRANSFER_ERROR", "detail": f"An unexpected error occurred: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
