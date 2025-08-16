import os
import stripe
import json
import logging
import decimal
from decimal import Decimal
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator
from django.db import transaction
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from marketplace.models import Cart, Order, OrderItem
from .models import PaymentTracker, WebhookEvent, PaymentTransaction, Payout, PayoutItem
from .serializers import PaymentTrackerSerializer, WebhookEventSerializer
from .email_utils import send_order_receipt_email, send_order_status_update_email, send_order_cancellation_receipt_email

# Set the Stripe API key from Django settings
stripe.api_key = settings.STRIPE_SECRET_KEY

# Add a check to ensure the key is loaded
if not stripe.api_key:
    raise ValueError("Stripe API key not found. Please set STRIPE_SECRET_KEY in your Django settings.")

# Initialize logger
logger = logging.getLogger(__name__)

User = get_user_model()

# Handle Stripe webhook events VERY VERY IMPORTANTE
@csrf_exempt
@require_POST
def stripe_webhook(request):
    payload = request.body
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET
    sig_header = request.headers.get('stripe-signature')

    if not endpoint_secret:
        print('⚠️  No endpoint secret configured. Skipping webhook verification.')
        # If no endpoint secret is configured, we won't verify the signature
        # and will just deserialize the event from JSON
    
    event = None
    
    try:
        event = stripe.Event.construct_from(
            json.loads(payload), stripe.api_key
        )
        print(f"🔔 Event constructed successfully: {event.type}")
    except ValueError as e:
        print(f"❌ Error constructing event: {e}")
        return HttpResponse(status=400)

    # Only verify the event if you've defined an endpoint secret
    # Otherwise, use the basic event deserialized with JSON
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except stripe.error.SignatureVerificationError as e:
        print('⚠️  Webhook signature verification failed.' + str(e))
        return HttpResponse(status=400, content='Webhook signature verification failed.')
    except Exception as e:
        print('❌ Error parsing webhook payload: ' + str(e))
        return HttpResponse(status=400, content='Webhook payload parsing failed.')

    print(f"🔔 Received Stripe event: {event.type}")
    print(f"🔔 Event data object type: {getattr(event.data.object, 'object', 'unknown')}")
    
    # Handle checkout.session.completed event (for embedded checkout)
    if event.type == 'checkout.session.completed':
        checkout_session = event.data.object
        print(f"🔔 Checkout session completed: {getattr(checkout_session, 'id', 'unknown')}")

        # Try to get metadata from checkout session
        metadata = getattr(checkout_session, 'metadata', {})
        print(f"🔔 Checkout session metadata: {metadata}")
        
        if metadata and metadata.get('user_id'):
            print(f"🔔 Found user_id in checkout session metadata: {metadata.get('user_id')}")
            
            # Pass the entire checkout session to handle_successful_payment
            handle_successful_payment(checkout_session)
        else:
            print("⚠️ No user_id found in checkout session metadata")
            print(f"⚠️ Available metadata keys: {list(metadata.keys()) if metadata else 'None'}")
            
            # Try to retrieve the full session from Stripe as fallback
            try:
                session_id = getattr(checkout_session, 'id')
                if session_id:
                    print(f"🔍 Attempting to retrieve full session: {session_id}")
                    full_session = stripe.checkout.Session.retrieve(session_id)
                    full_metadata = getattr(full_session, 'metadata', {})
                    print(f"🔍 Full session metadata: {full_metadata}")
                    
                    if full_metadata and full_metadata.get('user_id'):
                        print(f"✅ Found user_id in retrieved session: {full_metadata.get('user_id')}")
                        handle_successful_payment(full_session)
                        return HttpResponse(status=200, content='Webhook processed with retrieved session')
            except Exception as e:
                print(f"❌ Error retrieving full session: {e}")
            
            return HttpResponse(
                status=400, 
                content='No user_id found in checkout session metadata'
            )
    
    # Handle refund.updated event (for order cancellations)
    elif event.type == 'refund.updated':
        refund_object = event.data.object
        print(f"🔔 Refund updated event received")
        print(f"🔔 Refund object: {refund_object}")
        
        # Check if refund succeeded
        refund_status = getattr(refund_object, 'status', '')
        if refund_status == 'succeeded':
            refund_id = getattr(refund_object, 'id', '')
            refund_amount = getattr(refund_object, 'amount', 0) / 100  # Convert from cents
            refund_metadata = getattr(refund_object, 'metadata', {})
            
            print(f"🔔 Processing successful refund: {refund_id}, amount: ${refund_amount}")
            print(f"🔔 Refund metadata: {refund_metadata}")
            
            # Try to get order ID from refund metadata first
            order_id = refund_metadata.get('order_id')
            
            if order_id:
                print(f"🔔 Found order_id in refund metadata: {order_id}")
                try:
                    # Get order directly from metadata
                    from marketplace.models import Order
                    order = Order.objects.get(id=order_id)
                    
                    with transaction.atomic():
                        # Update order status to cancelled
                        order.status = 'cancelled'
                        order.payment_status = 'refunded'
                        order.save(update_fields=['status', 'payment_status'])
                        
                        # Restore stock for cancelled items
                        for item in order.items.all():
                            product = item.product
                            product.stock_quantity += item.quantity
                            product.save(update_fields=['stock_quantity'])
                            print(f"✅ Restored {item.quantity} units to product {product.name}")
                        
                        print(f"✅ Order {order.id} marked as cancelled due to refund")
                        
                        # Send cancellation confirmation email to customer
                        try:
                            # Get cancellation details from metadata
                            cancelled_by_id = refund_metadata.get('cancelled_by')
                            cancellation_reason = refund_metadata.get('reason', 'Order cancelled')
                            
                            email_sent, email_message = send_order_cancellation_receipt_email(
                                order, 
                                cancellation_reason, 
                                refund_amount
                            )
                            if email_sent:
                                print(f"📧 Cancellation email sent to {order.buyer.email}")
                            else:
                                print(f"⚠️ Failed to send cancellation email: {email_message}")
                        except Exception as email_error:
                            print(f"❌ Error sending cancellation email: {str(email_error)}")
                            # Don't fail the refund processing if email fails
                        
                except Order.DoesNotExist:
                    print(f"❌ Order {order_id} not found")
                except Exception as e:
                    print(f"❌ Error processing refund for order {order_id}: {e}")
            else:
                # Fallback: try to find order by payment tracker
                print("🔍 No order_id in metadata, searching by payment tracker")
                try:
                    payment_tracker = PaymentTracker.objects.filter(
                        stripe_refund_id=refund_id
                    ).first()
                    
                    if payment_tracker and payment_tracker.order:
                        order = payment_tracker.order
                        print(f"🔔 Found order {order.id} via payment tracker")
                        
                        with transaction.atomic():
                            # Update order status to cancelled
                            order.status = 'cancelled'
                            order.payment_status = 'refunded'
                            order.save(update_fields=['status', 'payment_status'])
                            
                            # Restore stock for cancelled items
                            for item in order.items.all():
                                product = item.product
                                product.stock_quantity += item.quantity
                                product.save(update_fields=['stock_quantity'])
                                print(f"✅ Restored {item.quantity} units to product {product.name}")
                            
                            print(f"✅ Order {order.id} marked as cancelled due to refund")
                            
                            # Send cancellation confirmation email to customer (fallback path)
                            try:
                                email_sent, email_message = send_order_cancellation_receipt_email(
                                    order, 
                                    'Order cancelled due to refund processing', 
                                    refund_amount
                                )
                                if email_sent:
                                    print(f"📧 Cancellation email sent to {order.buyer.email} (fallback)")
                                else:
                                    print(f"⚠️ Failed to send cancellation email (fallback): {email_message}")
                            except Exception as email_error:
                                print(f"❌ Error sending cancellation email (fallback): {str(email_error)}")
                                # Don't fail the refund processing if email fails
                    else:
                        print(f"⚠️ No payment tracker found for refund {refund_id}")
                        
                except Exception as e:
                    print(f"❌ Error processing refund webhook: {e}")
        else:
            print(f"ℹ️ Refund status is {refund_status}, skipping processing")
    
    # Handle payment_intent.succeeded event (fallback)
    elif event.type == 'payment_intent.succeeded':
     """payment_intent = event.data.object
        print(f"🔔 Payment intent succeeded: {getattr(payment_intent, 'id', 'unknown')}")

        # Try to get metadata from payment intent
        metadata = getattr(payment_intent, 'metadata', {})
        print(f"🔔 Payment intent metadata: {metadata}")
        
        if metadata and metadata.get('user_id'):
            print(f"🔔 Found user_id in payment_intent metadata: {metadata.get('user_id')}")
            
            # Create a session object with payment_intent data
            mock_session = {
                'id': getattr(payment_intent, 'id', 'unknown'),
                'amount_total': getattr(payment_intent, 'amount', 0),
                'metadata': dict(metadata) if metadata else {},
                'payment_status': 'paid',
                'total_details': {
                    'amount_tax': 0  # Payment intents don't have tax breakdown
                },
                'shipping_details': getattr(payment_intent, 'shipping', {}),
                'customer_details': {}
            }
            handle_successful_payment(mock_session)
        else:
            print("⚠️ No user_id found in payment_intent metadata")
            print(f"⚠️ Available metadata keys: {list(metadata.keys()) if metadata else 'None'}")
            
            # Try to find the associated checkout session
            try:
                # Look for latest_charge and then find associated session
                latest_charge_id = getattr(payment_intent, 'latest_charge')
                if latest_charge_id:
                    print(f"🔍 Looking for checkout sessions with charge: {latest_charge_id}")
                    # This is a workaround - in production you might need to store session IDs
                    print("⚠️ Cannot retrieve checkout session from payment_intent. Consider using checkout.session.completed events instead.")
            except Exception as e:
                print(f"❌ Error looking for checkout session: {e}")
            
            return HttpResponse(
                status=400, 
                content='No user_id found in payment_intent metadata, skipping processing'
            )"""
    
    # Handle account.updated event (for Stripe Connect seller account updates)
    elif event.type == 'account.updated':
        account_object = event.data.object
        account_id = getattr(account_object, 'id', '')
        print(f"🔔 Account updated event received for account: {account_id}")
        
        try:
            # Import the service here to avoid circular imports
            from .stripe_service import StripeConnectService
            
            # Process the account update
            result = StripeConnectService.handle_account_updated_webhook(
                account_id, 
                account_object
            )
            
            if result['success']:
                print(f"✅ Successfully processed account update for account: {account_id}")
                print(f"✅ Updated user ID: {result.get('user_id', 'unknown')}")
            else:
                print(f"⚠️ Failed to process account update: {result['errors']}")
                
        except Exception as e:
            print(f"❌ Error processing account.updated webhook: {e}")
            # Don't fail the webhook for account update errors
    
    # Handle transfer.created events for payment verification
    elif event.type == 'transfer.created':
        transfer_object = event.data.object

        print(f"🔔 Event Type: {event.type}")
        # Extract transfer data based on the actual Stripe structure
        transfer_id = getattr(transfer_object, 'id', '')  # e.g., "tr_1RwA18CEfT6kDqKIZfcknZlv"
        amount = getattr(transfer_object, 'amount', 0)    # e.g., 205106 (in cents)
        currency = getattr(transfer_object, 'currency', '') # e.g., "eur"
        destination = getattr(transfer_object, 'destination', '') # e.g., "acct_1Rw2CuFhtX16wVcQ"
        metadata = getattr(transfer_object, 'metadata', {})
        reversed = getattr(transfer_object, 'reversed', False)
        
        # Log the transfer details
        logger.info(f"[WEBHOOK] Transfer created: {transfer_id}")
        logger.info(f"[WEBHOOK] Transfer amount: {amount} {currency}")
        logger.info(f"[WEBHOOK] Transfer destination: {destination}")
        logger.info(f"[WEBHOOK] Transfer reversed: {reversed}")
        logger.info(f"[WEBHOOK] Transfer metadata: {metadata}")
        
        try:
            # Extract transaction_id from metadata (from your example)
            transaction_id = metadata.get('transaction_id')  # "19220fe2-3c3b-45dc-8995-a750ba8e3982"
            order_id = metadata.get('order_id')             # "b6df43cd-4d40-49fb-bb33-adb7a390fa65"
            seller_id = metadata.get('seller_id')           # "1"
            buyer_id = metadata.get('buyer_id')             # "1"
            
            print(f"🔍 Extracted from metadata:")
            print(f"   Transaction ID: {transaction_id}")
            print(f"   Order ID: {order_id}")
            print(f"   Seller ID: {seller_id}")
            print(f"   Buyer ID: {buyer_id}")
            
            if transaction_id:
                try:
                    payment_transaction = PaymentTransaction.objects.get(id=transaction_id)
                    logger.info(f"[WEBHOOK] Found payment transaction {transaction_id}")
                    print(f"✅ Found PaymentTransaction: {payment_transaction.id}")
                    print(f"   Current status: {payment_transaction.status}")
                    print(f"   Current transfer_id: {payment_transaction.transfer_id}")
                    
                    # Since this is transfer.created, the transfer was successfully created
                    # This means the transfer is now "paid" and completed
                    if not reversed:
                        success = payment_transaction.complete_transfer(
                            notes=f"Transfer completed via webhook: {transfer_id} (amount: {amount/100:.2f} {currency.upper()})"
                        )
                        if success:
                            logger.info(f"[SUCCESS] Payment transaction {transaction_id} marked as completed")
                            print(f"✅ Transfer {transfer_id} completed successfully - payment released to seller")
                            print(f"   Amount: {amount/100:.2f} {currency.upper()}")
                            print(f"   New status: {payment_transaction.status}")
                        else:
                            logger.error(f"[ERROR] Failed to mark transaction {transaction_id} as completed")
                            print(f"❌ Failed to update transaction status")
                    else:
                        # Transfer was reversed - this would be unusual for a .created event
                        logger.warning(f"[REVERSED] Transfer {transfer_id} was reversed")
                        print(f"⚠️ Transfer {transfer_id} was reversed - unusual for created event")
                        
                    # Update metadata with webhook information
                    if hasattr(payment_transaction, 'metadata') and payment_transaction.metadata:
                        payment_transaction.metadata.update({
                            'webhook_transfer_id': transfer_id,
                            'webhook_received': timezone.now().isoformat(),
                            'webhook_amount': amount,
                            'webhook_currency': currency,
                            'webhook_destination': destination,
                            'webhook_event_type': 'transfer.created'
                        })
                        payment_transaction.save(update_fields=['metadata', 'updated_at'])
                        print(f"📝 Updated transaction metadata with webhook info")
                        
                except PaymentTransaction.DoesNotExist:
                    logger.error(f"[ERROR] Payment transaction {transaction_id} not found")
                    print(f"❌ PaymentTransaction {transaction_id} not found in database")
                    
            else:
                logger.warning(f"[WARNING] No transaction_id found in transfer metadata")
                print(f"⚠️ No transaction_id found in transfer metadata")
                print(f"   Available metadata keys: {list(metadata.keys())}")
                
        except Exception as e:
            logger.error(f"[ERROR] Error processing transfer.created webhook: {e}")
            print(f"❌ Error processing transfer webhook: {e}")
            import traceback
            traceback.print_exc()
            # Don't fail the webhook for transfer processing errors

    # Handle payout.paid, payout.failed, and payout.updated events
    elif event.type in ['payout.paid', 'payout.failed', 'payout.updated', 'payout.canceled']:
        payout_object = event.data.object
        


        print(f"🔔 ==================== PAYOUT WEBHOOK EVENT ====================")
        print(f"🔔 Event Type: {event.type}")
        print(f"🔔 Event ID: {getattr(event, 'id', 'unknown')}")
        print(f"🔔 Created: {getattr(event, 'created', 'unknown')}")
        print(f"🔔 Payout Object:")
        print(f"🔔 {json.dumps(payout_object, indent=2, default=str)}")
        print(f"🔔 ===============================================================")
        
        """try:
            stripe_payout_id = getattr(payout_object, 'id', None)
            payout_status = getattr(payout_object, 'status', None)
            payout_amount = getattr(payout_object, 'amount', None)
            payout_currency = getattr(payout_object, 'currency', None)
            payout_arrival_date = getattr(payout_object, 'arrival_date', None)
            payout_metadata = getattr(payout_object, 'metadata', {})
            
            print(f"📊 Payout Details:")
            print(f"   Stripe Payout ID: {stripe_payout_id}")
            print(f"   Status: {payout_status}")
            print(f"   Amount: {payout_amount/100 if payout_amount else 0:.2f} {payout_currency.upper() if payout_currency else 'unknown'}")
            print(f"   Arrival Date: {payout_arrival_date}")
            print(f"   Metadata: {payout_metadata}")
            
            if stripe_payout_id:
                try:
                    payout = Payout.objects.get(stripe_payout_id=stripe_payout_id)
                    logger.info(f"[WEBHOOK] Found payout {payout.id} for Stripe payout {stripe_payout_id}")
                    print(f"✅ Found Payout: {payout.id}")
                    print(f"   Current status: {payout.status}")
                    print(f"   Amount: {payout.amount_formatted}")
                    print(f"   Seller: {payout.seller.username}")
                    
                    # Update payout status and details
                    payout.status = payout_status
                    
                    # Update arrival date if provided
                    if payout_arrival_date:
                        payout.arrival_date = timezone.datetime.fromtimestamp(
                            payout_arrival_date, tz=timezone.utc
                        )
                    
                    # Handle failure information
                    if event.type == 'payout.failed':
                        failure_code = getattr(payout_object, 'failure_code', None)
                        failure_message = getattr(payout_object, 'failure_message', None)
                        
                        payout.failure_code = failure_code or 'unknown'
                        payout.failure_message = failure_message or 'Payout failed'
                        
                        logger.error(f"[WEBHOOK] Payout {payout.id} failed: {failure_code} - {failure_message}")
                        print(f"❌ Payout failed: {failure_code} - {failure_message}")
                        
                        # Update fields for failed payout
                        payout.save(update_fields=[
                            'status', 'failure_code', 'failure_message', 
                            'arrival_date', 'updated_at'
                        ])
                    else:
                        # Update fields for successful status update
                        payout.save(update_fields=[
                            'status', 'arrival_date', 'updated_at'
                        ])
                    
                    logger.info(f"[SUCCESS] Payout {payout.id} updated with status: {payout_status}")
                    print(f"✅ Payout status updated to: {payout_status}")
                    
                    # Update metadata with webhook information
                    if hasattr(payout, 'metadata') and payout.metadata:
                        payout.metadata.update({
                            'webhook_event_type': event.type,
                            'webhook_received': timezone.now().isoformat(),
                            'webhook_status': payout_status,
                            'webhook_arrival_date': payout_arrival_date,
                            'last_webhook_event_id': getattr(event, 'id', 'unknown')
                        })
                        payout.save(update_fields=['metadata', 'updated_at'])
                        print(f"📝 Updated payout metadata with webhook info")
                    
                except Payout.DoesNotExist:
                    logger.error(f"[ERROR] Payout with stripe_payout_id {stripe_payout_id} not found")
                    print(f"❌ Payout {stripe_payout_id} not found in database")
                    
            else:
                logger.warning(f"[WARNING] No stripe_payout_id found in payout object")
                print(f"⚠️ No stripe_payout_id found in payout object")
                
        except Exception as e:
            logger.error(f"[ERROR] Error processing {event.type} webhook: {e}")
            print(f"❌ Error processing payout webhook: {e}")
            import traceback
            traceback.print_exc()
            # Don't fail the webhook for payout processing errors"""
            
    else:
        print(f"ℹ️ Unhandled event type: {event.type}")

    return HttpResponse(status=200, content='Webhook received and processed successfully.')


def stripe_webhook_connect(request):
    """
    Handle Stripe Connect webhooks for seller account updates
    """
    payload = request.body
    endpoint_secret = settings.STRIPE_WEBHOOK_CONNECT_SECRET
    sig_header = request.headers.get('stripe-signature')

    if not endpoint_secret:
        print('⚠️  No endpoint secret configured. Skipping webhook verification.')
        # If no endpoint secret is configured, we won't verify the signature
        # and will just deserialize the event from JSON
    
    event = None
    
    try:
        event = stripe.Event.construct_from(
            json.loads(payload), stripe.api_key
        )
        print(f"🔔 Event constructed successfully: {event.type}")
    except ValueError as e:
        print(f"❌ Error constructing event: {e}")
        return HttpResponse(status=400)

    # Only verify the event if you've defined an endpoint secret
    # Otherwise, use the basic event deserialized with JSON
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except stripe.error.SignatureVerificationError as e:
        print('⚠️  Webhook signature verification failed.' + str(e))
        return HttpResponse(status=400, content='Webhook signature verification failed.')
    except Exception as e:
        print('❌ Error parsing webhook payload: ' + str(e))
        return HttpResponse(status=400, content='Webhook payload parsing failed.')

    print(f"🔔 Received Stripe event: {event.type}")
    if event.type in ['payout.paid', 'payout.failed', 'payout.updated', 'payout.canceled']:
        payout_object = event.data.object
        


        print(f"🔔 ==================== PAYOUT WEBHOOK EVENT ====================")
        print(f"🔔 Event Type: {event.type}")
        print(f"🔔 Event ID: {getattr(event, 'id', 'unknown')}")
        print(f"🔔 Created: {getattr(event, 'created', 'unknown')}")
        print(f"🔔 Payout Object:")
        print(f"🔔 {json.dumps(payout_object, indent=2, default=str)}")
        print(f"🔔 ===============================================================")
        
        try:
            stripe_payout_id = getattr(payout_object, 'id', None)
            payout_status = getattr(payout_object, 'status', None)
            payout_amount = getattr(payout_object, 'amount', None)
            payout_currency = getattr(payout_object, 'currency', None)
            payout_arrival_date = getattr(payout_object, 'arrival_date', None)
            payout_metadata = getattr(payout_object, 'metadata', {})
            
            print(f"📊 Payout Details:")
            print(f"   Stripe Payout ID: {stripe_payout_id}")
            print(f"   Status: {payout_status}")
            print(f"   Amount: {payout_amount/100 if payout_amount else 0:.2f} {payout_currency.upper() if payout_currency else 'unknown'}")
            print(f"   Arrival Date: {payout_arrival_date}")
            print(f"   Metadata: {payout_metadata}")
            
            if stripe_payout_id:
                try:
                    payout = Payout.objects.get(stripe_payout_id=stripe_payout_id)
                    logger.info(f"[WEBHOOK] Found payout {payout.id} for Stripe payout {stripe_payout_id}")
                    print(f"✅ Found Payout: {payout.id}")
                    print(f"   Current status: {payout.status}")
                    print(f"   Amount: {payout.amount_formatted}")
                    print(f"   Seller: {payout.seller.username}")
                    
                    # Update payout status and details
                    payout.status = payout_status
                    
                    # Update arrival date if provided
                    if payout_arrival_date:
                        payout.arrival_date = timezone.datetime.fromtimestamp(
                            payout_arrival_date, tz=timezone.utc
                        )
                    
                    # Handle failure information
                    if event.type == 'payout.failed':
                        failure_code = getattr(payout_object, 'failure_code', None)
                        failure_message = getattr(payout_object, 'failure_message', None)
                        
                        payout.failure_code = failure_code or 'unknown'
                        payout.failure_message = failure_message or 'Payout failed'
                        
                        logger.error(f"[WEBHOOK] Payout {payout.id} failed: {failure_code} - {failure_message}")
                        print(f"❌ Payout failed: {failure_code} - {failure_message}")
                        
                        # Update fields for failed payout
                        payout.save(update_fields=[
                            'status', 'failure_code', 'failure_message', 
                            'arrival_date', 'updated_at'
                        ])
                    else:
                        # Update fields for successful status update
                        payout.save(update_fields=[
                            'status', 'arrival_date', 'updated_at'
                        ])
                    
                    logger.info(f"[SUCCESS] Payout {payout.id} updated with status: {payout_status}")
                    print(f"✅ Payout status updated to: {payout_status}")
                    
                    # Update metadata with webhook information
                    if hasattr(payout, 'metadata') and payout.metadata:
                        payout.metadata.update({
                            'webhook_event_type': event.type,
                            'webhook_received': timezone.now().isoformat(),
                            'webhook_status': payout_status,
                            'webhook_arrival_date': payout_arrival_date,
                            'last_webhook_event_id': getattr(event, 'id', 'unknown')
                        })
                        payout.save(update_fields=['metadata', 'updated_at'])
                        print(f"📝 Updated payout metadata with webhook info")
                    
                except Payout.DoesNotExist:
                    logger.error(f"[ERROR] Payout with stripe_payout_id {stripe_payout_id} not found")
                    print(f"❌ Payout {stripe_payout_id} not found in database")
                    
            else:
                logger.warning(f"[WARNING] No stripe_payout_id found in payout object")
                print(f"⚠️ No stripe_payout_id found in payout object")
                
        except Exception as e:
            logger.error(f"[ERROR] Error processing {event.type} webhook: {e}")
            print(f"❌ Error processing payout webhook: {e}")
            import traceback
            traceback.print_exc()
            # Don't fail the webhook for payout processing errors"""
    else :
        print(f"ℹ️ Unhandled event type: {event.type}")

    return HttpResponse(status=200, content='Webhook received but not successfully.')



# Create PaymentTransaction records for each seller in the order
def create_payment_transactions(order, session):
    """
    Create PaymentTransaction records for each seller in the order
    This tracks payments per seller with integrated 30-day holding periods
    """
    from collections import defaultdict
    from decimal import Decimal
    
    try:
        print(f"🔄 Creating payment transactions for order {order.id}")
        
        # Get Stripe session info
        stripe_payment_intent_id = session.get('payment_intent', '')
        stripe_checkout_session_id = session.get('id', '')
        total_amount = Decimal(session['amount_total']) / 100  # Convert from cents
        
        # Group order items by seller
        sellers_data = defaultdict(lambda: {
            'items': [],
            'total_amount': Decimal('0.00'),
            'item_count': 0,
            'item_names': []
        })
        
        for order_item in order.items.all():
            seller = order_item.seller
            sellers_data[seller]['items'].append(order_item)
            sellers_data[seller]['total_amount'] += order_item.total_price
            sellers_data[seller]['item_count'] += order_item.quantity
            sellers_data[seller]['item_names'].append(order_item.product_name)
        
        print(f"📊 Found {len(sellers_data)} sellers in order")
        
        # Create PaymentTransaction for each seller
        for seller, seller_data in sellers_data.items():
            print(f"💰 Creating payment transaction for seller: {seller.username}")
            
            # Calculate fees (you can adjust these percentages)
            gross_amount = seller_data['total_amount']
            platform_fee_rate = Decimal('0.05')  # 5% platform fee
            stripe_fee_rate = Decimal('0.029')   # 2.9% Stripe fee + $0.30
            stripe_fixed_fee = Decimal('0.30')
            
            platform_fee = gross_amount * platform_fee_rate
            stripe_fee = (gross_amount * stripe_fee_rate) + stripe_fixed_fee
            net_amount = gross_amount - platform_fee - stripe_fee
            
            # Create PaymentTransaction with integrated hold system
            payment_transaction = PaymentTransaction.objects.create(
                stripe_payment_intent_id=stripe_payment_intent_id,
                stripe_checkout_session_id=stripe_checkout_session_id,
                order=order,
                seller=seller,
                buyer=order.buyer,
                status='held',  # Start with held status
                gross_amount=gross_amount,
                platform_fee=platform_fee,
                stripe_fee=stripe_fee,
                net_amount=net_amount,
                currency='USD',
                item_count=seller_data['item_count'],
                item_names=', '.join(seller_data['item_names']),
                payment_received_date=timezone.now(),
                # Integrated hold fields - all payments held for 30 days
                hold_reason='standard',
                days_to_hold=30,  # Standard 30-day hold
                hold_start_date=timezone.now(),
                hold_notes=f"Standard 30-day hold period for marketplace transactions",
                metadata={
                    'order_id': str(order.id),
                    'stripe_session_id': stripe_checkout_session_id,
                    'seller_id': str(seller.id),
                    'buyer_id': str(order.buyer.id)
                }
            )
            
            print(f"✅ Created payment transaction {payment_transaction.id} for ${net_amount} with 30-day hold")
        
        print(f"✅ Successfully created payment tracking for order {order.id}")
        
    except Exception as e:
        print(f"❌ Error creating payment transactions: {str(e)}")
        raise

# Handle successful payment by updating existing order status this is for Stripe Webhook handling
def handle_successful_payment(session):
    """
    Handle successful payment by updating existing order status
    """
    print("🔔 Handling successful payment...")
    print(f"Session ID: {session.get('id', 'Unknown')}")
    print(f"Session data keys: {list(session.keys()) if isinstance(session, dict) else 'Not a dict'}")
    
    try:
        with transaction.atomic():
            # Extract user_id and order_id from metadata
            user_id = session['metadata'].get('user_id')
            order_id = session['metadata'].get('order_id')
            
            if not user_id:
                print(f"❌ Missing user_id in session metadata")
                return False
                
            if not order_id:
                print(f"❌ Missing order_id in session metadata")
                return False
                
            # Get user and verify they exist
            User = get_user_model()
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist as e:
                print(f"❌ User not found: {e}")
                return False
                
            # Get the existing order and verify ownership
            try:
                order = Order.objects.get(id=order_id)
                
                # Verify the user owns this order
                if order.buyer != user:
                    print(f"❌ Order {order_id} does not belong to user {user_id}")
                    return False
                    
                # Verify order is in pending_payment status
                if order.status != 'pending_payment':
                    print(f"⚠️ Order {order_id} is not in pending_payment status (current: {order.status})")
                    # We still continue to update payment info, but log this
                    
            except Order.DoesNotExist:
                print(f"❌ Order {order_id} not found")
                return False
                
            # Get shipping and billing address from session
            shipping_details = session.get('shipping_details', {})
            customer_details = session.get('customer_details', {})
            
            # Prepare shipping address
            shipping_address = {}
            if shipping_details and shipping_details.get('address'):
                shipping_address = {
                    'name': shipping_details.get('name', ''),
                    'line1': shipping_details['address'].get('line1', ''),
                    'line2': shipping_details['address'].get('line2', ''),
                    'city': shipping_details['address'].get('city', ''),
                    'state': shipping_details['address'].get('state', ''),
                    'postal_code': shipping_details['address'].get('postal_code', ''),
                    'country': shipping_details['address'].get('country', ''),
                }
            elif customer_details and customer_details.get('address'):
                # Fallback to billing address if shipping not available
                shipping_address = {
                    'name': customer_details.get('name', ''),
                    'line1': customer_details['address'].get('line1', ''),
                    'line2': customer_details['address'].get('line2', ''),
                    'city': customer_details['address'].get('city', ''),
                    'state': customer_details['address'].get('state', ''),
                    'postal_code': customer_details['address'].get('postal_code', ''),
                    'country': customer_details['address'].get('country', ''),
                }
                
            # Calculate payment amounts from Stripe session
            tax_amount = Decimal(session.get('total_details', {}).get('amount_tax', 0)) / 100  # Convert from cents
            total_amount = Decimal(session['amount_total']) / 100  # Convert from cents
            
            # Update the existing order with payment confirmation
            order.status = 'payment_confirmed'  # Update status to payment confirmed
            order.payment_status = 'paid'  # Update payment status to paid
            order.tax_amount = tax_amount  # Update tax amount from Stripe
            order.total_amount = total_amount  # Update total amount from Stripe
            order.shipping_address = shipping_address  # Update shipping address from checkout
            order.is_locked = True  # Lock the order after payment
            order.save(update_fields=['status', 'payment_status', 'tax_amount', 'total_amount', 'shipping_address', 'is_locked'])
            
            print(f"📦 Order {order.id} updated to 'payment_confirmed' status with payment_status 'paid'")
            
            # Create payment tracker for this order
            stripe_payment_intent_id = session.get('payment_intent', session.get('id', ''))
            PaymentTracker.objects.create(
                stripe_payment_intent_id=stripe_payment_intent_id,
                order=order,
                user=user,
                transaction_type='payment',
                status='succeeded',
                amount=total_amount,
                currency='USD',
                notes=f'Order payment completed via Stripe session {session.get("id", "unknown")}'
            )
            print(f"💳 Payment tracker created for order {order.id}")
            
            # Create detailed payment tracking records per seller (manual processing for now)
            print(f"🔄 Creating detailed payment transactions for order {order.id}")
            create_payment_transactions(order, session)
            print(f"📊 Detailed payment transactions created for order {order.id} - MANUAL RELEASE REQUIRED")
            
            print(f"✅ Order {order.id} payment confirmed successfully with {order.items.count()} items")
            
            # Send order receipt email to customer
            try:
                email_sent, email_message = send_order_receipt_email(order)
                if email_sent:
                    print(f"📧 Order receipt email sent to {user.email}")
                else:
                    print(f"⚠️ Failed to send receipt email: {email_message}")
            except Exception as email_error:
                print(f"❌ Error sending receipt email: {str(email_error)}")
                # Don't fail the order confirmation if email fails
            
            return True
            
    except Exception as e:
        print(f"❌ Error handling successful payment: {str(e)}")
        return False

# Create a Stripe Embedded Checkout Session
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_checkout_session(request):
    """
    Create a Stripe Embedded Checkout Session
    """
    try:
        # Get the user's cart
        cart = Cart.get_or_create_cart(user=request.user)
        cart_items = cart.items.all()
        
        if not cart_items.exists():
            return Response({
                'error': 'EMPTY_CART',
                'detail': 'Your cart is empty'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Prepare line items for Stripe
        line_items = []
        for item in cart_items:
            if item.product.stock_quantity < item.quantity:
                return Response({
                    'error': 'INSUFFICIENT_STOCK',
                    'detail': f'Insufficient stock for product {item.product.name}'
                }, status=status.HTTP_400_BAD_REQUEST)
            # Prepare line item for each product in the cart
            if item.product.price <= 0:
                return Response({
                    'error': 'INVALID_PRICE',
                    'detail': f'Invalid price for product {item.product.name}'
                }, status=status.HTTP_400_BAD_REQUEST)
            if item.quantity <= 0:
                return Response({
                    'error': 'INVALID_QUANTITY',
                    'detail': f'Invalid quantity for product {item.product.name}'
                }, status=status.HTTP_400_BAD_REQUEST)
            # Add product line item
            line_items.append({
                'price_data': {
                    'currency': 'usd',
                    'unit_amount': int(item.product.price * 100),  # Convert to cents
                    'product_data': {
                        'name': item.product.name,
                        'description': item.product.short_description or item.product.description[:100],
                        'images': [item.product.images.filter(is_primary=True).first().image.url] if item.product.images.filter(is_primary=True).exists() else [],
                    },
                },
                'quantity': item.quantity,
            })
        
        # Add shipping line item
        line_items.append({
            'price_data': {
                'currency': 'usd',
                'unit_amount': 1999,  # $19.99 shipping
                'product_data': {
                    'name': 'Shipping',
                    'description': 'Standard shipping',
                },
            },
            'quantity': 1,
        })
        
        # Create order with pending_payment status before Stripe session
        print(f"🔔 Creating order with pending_payment status for user {request.user.id}")
        
        with transaction.atomic():
            # Calculate totals from cart
            subtotal = sum(item.total_price for item in cart_items)
            shipping_cost = Decimal('19.99')  # Fixed shipping for now
            total_amount = subtotal + shipping_cost
            
            # Create the order with pending_payment status
            order = Order.objects.create(
                buyer=request.user,
                status='pending_payment',  # Order starts as pending payment
                payment_status='pending',  # Payment status is pending
                subtotal=subtotal,
                shipping_cost=shipping_cost,
                tax_amount=Decimal('0.00'),  # Will be calculated by Stripe
                total_amount=total_amount,
                shipping_address={},  # Will be filled by Stripe checkout
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
                    product_image=product.images.filter(is_primary=True).first().image.url if product.images.filter(is_primary=True).exists() else '',
                )
                
                # Reserve stock (reduce stock quantity immediately)
                if product.stock_quantity >= cart_item.quantity:
                    product.stock_quantity -= cart_item.quantity
                    product.save(update_fields=['stock_quantity'])
                    print(f"📦 Reserved {cart_item.quantity} units of {product.name}")
                else:
                    print(f"⚠️ Warning: Insufficient stock for product {product.name}")
                    # In a production system, you might want to handle this differently
                    
            print(f"✅ Order {order.id} created successfully with {cart_items.count()} items")
            
            # Clear cart after order creation
            cart.clear_items()
            print(f"🛒 Cart cleared for user {request.user.username}")
        
        print(f"🔔 Creating Stripe checkout session for order {order.id}")
        # Create Stripe Embedded Checkout Session with order_id instead of cart_id
        session = stripe.checkout.Session.create(
            ui_mode='embedded',
            locale=str(request.user.language) or 'en',
            line_items=line_items,
            mode='payment',
            automatic_tax={'enabled': True},
            payment_intent_data={
                'transfer_group': f'ORDER{order.id}'  # Group transfers by order ID
            },
            return_url=f"http://localhost:5173/order-success/{order.id}",
            metadata={
                "user_id": str(request.user.id),
                "order_id": str(order.id),  # Pass order_id instead of cart_id
            },

            billing_address_collection='required',
        )
        
        print(f"✅ Checkout session created: {session.id}")
        print(f"✅ Session metadata: {session.metadata}")
        print(f"✅ Session client_secret: {session.client_secret[:20]}...")
        
        return JsonResponse({
            'clientSecret': session.client_secret
        })
        
    except Exception as e:
        logger.error(f"Error creating checkout session: {str(e)}")
        return Response({
            'error': 'CHECKOUT_SESSION_CREATION_FAILED',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def checkout_session_status(request):
    """
    Check the status of a Stripe Checkout Session
    """
    session_id = request.GET.get('session_id')
    
    if not session_id:
        return Response({
            'error': 'MISSING_SESSION_ID',
            'detail': 'session_id parameter is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        
        session = stripe.checkout.Session.retrieve(session_id)
        
        return Response({
            'status': session.status,
            'payment_status': session.payment_status,
            'customer_email': session.customer_details.email if session.customer_details else None,
            'amount_total': session.amount_total,
            'currency': session.currency,
        })
        
    except Exception as e:
        logger.error(f"Error retrieving checkout session: {str(e)}")
        return Response({
            'error': 'SESSION_RETRIEVAL_FAILED',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# Cancel an order and process Stripe refund if payment was made
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cancel_order(request, order_id):
    """
    Cancel an order and process Stripe refund if payment was made
    """
    try:
        # Get the order
        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return Response({
                'error': 'ORDER_NOT_FOUND',
                'detail': 'Order not found'
            }, status=status.HTTP_404_NOT_FOUND)

        # Verify user permissions
        user_owns_items = order.items.filter(seller=request.user).exists()
        is_buyer = order.buyer == request.user
        is_staff = request.user.is_staff

        if not (user_owns_items or is_buyer or is_staff):
            return Response({
                'error': 'PERMISSION_DENIED',
                'detail': 'You must be the seller of at least one item or the buyer to cancel this order'
            }, status=status.HTTP_403_FORBIDDEN)

        # Check if order can be cancelled
        if order.status in ['shipped', 'delivered', 'cancelled', 'refunded']:
            return Response({
                'error': 'CANNOT_CANCEL',
                'detail': f'Order cannot be cancelled. Current status: {order.status}. Orders can only be cancelled before shipping.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get cancellation reason from request
        cancellation_reason = request.data.get('cancellation_reason', '')
        if not cancellation_reason:
            return Response({
                'error': 'MISSING_REASON',
                'detail': 'Cancellation reason is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            # Check if payment needs to be refunded
            refund_processed = False
            refund_amount = Decimal('0.00')
            stripe_refund_id = None

            # Only process refund if payment was completed
            if order.payment_status == 'paid':
                try:
                    # Try to find payment tracker in our system first
                    payment_tracker = PaymentTracker.objects.filter(
                        order=order, 
                        transaction_type='payment', 
                        status='succeeded'
                    ).first()

                    # If we have a payment tracker, use it for refund
                    if payment_tracker and payment_tracker.stripe_payment_intent_id:
                        refund_amount = payment_tracker.amount

                        # Create refund through Stripe
                        stripe_refund = stripe.Refund.create(
                            payment_intent=payment_tracker.stripe_payment_intent_id,
                            amount=int(refund_amount * 100),  # Convert to cents
                            reason='requested_by_customer',
                            metadata={
                                'order_id': str(order.id),
                                'cancelled_by': str(request.user.id),
                                'reason': cancellation_reason,
                            }
                        )

                        stripe_refund_id = stripe_refund.id

                        # Create refund tracker
                        PaymentTracker.objects.create(
                            stripe_refund_id=stripe_refund_id,
                            order=order,
                            user=request.user,
                            transaction_type='refund',
                            status='succeeded',
                            amount=refund_amount,
                            currency='USD',
                            notes=f'Order cancelled: {cancellation_reason}'
                        )

                        refund_processed = True
                        logger.info(f"Stripe refund processed: {stripe_refund_id} for order {order.id}")

                except stripe.error.StripeError as stripe_error:
                    logger.error(f"Stripe refund failed: {str(stripe_error)}")
                    return Response({
                        'error': 'REFUND_FAILED',
                        'detail': f'Failed to process refund: {str(stripe_error)}',
                        'stripe_error': str(stripe_error)
                    }, status=status.HTTP_400_BAD_REQUEST)

                except Exception as refund_error:
                    logger.error(f"Refund processing failed: {str(refund_error)}")
                    return Response({
                        'error': 'REFUND_ERROR',
                        'detail': f'Error processing refund: {str(refund_error)}'
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Store cancellation request data but don't update order status yet
            # Order status will be updated by webhook when refund is confirmed
            order.cancellation_reason = cancellation_reason
            order.cancelled_by = request.user
            order.cancelled_at = timezone.now()
            order.save(update_fields=['cancellation_reason', 'cancelled_by', 'cancelled_at'])

            # Log the cancellation request
            logger.info(f"Cancellation requested for order {order.id} by user {request.user.username}. Refund initiated: {refund_processed}")

            return Response({
                'success': True,
                'message': 'Cancellation request submitted. Order status will be updated when refund is processed.' if refund_processed else 'Order cancelled successfully.',
                'refund_requested': refund_processed,
                'refund_amount': str(refund_amount) if refund_processed else None,
                'stripe_refund_id': stripe_refund_id,
                'order': {
                    'id': str(order.id),
                    'status': order.status,  # Keep current status
                    'payment_status': order.payment_status,  # Keep current payment status
                    'cancelled_at': order.cancelled_at.isoformat() if order.cancelled_at else None,
                    'cancellation_reason': order.cancellation_reason,
                    'cancelled_by': {
                        'id': order.cancelled_by.id,
                        'username': order.cancelled_by.username
                    } if order.cancelled_by else None
                }
            }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error cancelling order {order_id}: {str(e)}")
        return Response({
            'error': 'ORDER_CANCELLATION_FAILED',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Stripe Connect Views for Seller Account Management

from .stripe_service import StripeConnectService

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def stripe_account(request):
    """
    Unified Stripe account endpoint:
    - GET: Retrieve existing account info or eligibility status
    - POST: Create new account if user doesn't have one, or return existing account info
    
    Required security validations:
    - User must be authenticated (handled by @permission_classes([IsAuthenticated]))
    - For regular users: Must have password and 2FA enabled
    - For OAuth users: No additional requirements (authenticated via OAuth provider)
    """
    try:
        user = request.user
        
        if request.method == 'GET':
            print(f"🔍 GET /stripe/account for user: {user.email}")
            
            # Check if user already has a Stripe account
            if user.stripe_account_id:
                print(f"✅ User has existing account: {user.stripe_account_id}")
                
                # Get account status using the service
                result = StripeConnectService.get_account_status(user)
                
                if result['success']:
                    return Response({
                        'has_account': True,
                        'account_id': result['account_id'],
                        'status': result['status'],
                        'details_submitted': result['details_submitted'],
                        'charges_enabled': result['charges_enabled'],
                        'payouts_enabled': result['payouts_enabled'],
                        'requirements': result['requirements'],
                        'message': 'Account exists and details retrieved successfully.'
                    }, status=status.HTTP_200_OK)
                else:
                    return Response({
                        'error': 'Failed to get account status.',
                        'details': result['errors']
                    }, status=status.HTTP_400_BAD_REQUEST)
            else:
                print("ℹ️ User doesn't have account, checking eligibility...")
                
                # Check eligibility for account creation
                validation = StripeConnectService.validate_seller_requirements(user)
                
                return Response({
                    'has_account': False,
                    'eligible_for_creation': validation['valid'],
                    'eligibility_errors': validation['errors'],
                    'requirements': {
                        'is_authenticated': True,
                        'is_oauth_user': user.is_oauth_only_user(),
                        'has_password': user.has_usable_password(),
                        'two_factor_enabled': getattr(user, 'two_factor_enabled', False),
                    },
                    'message': 'No account exists. Check eligibility for creation.'
                }, status=status.HTTP_200_OK)
        
        elif request.method == 'POST':
            print(f"🔄 POST /stripe/account for user: {user.email}")
            
            # Check if user already has account
            if user.stripe_account_id:
                print(f"ℹ️ User already has account: {user.stripe_account_id}, returning account info")
                
                # Return existing account info instead of creating new one
                result = StripeConnectService.get_account_status(user)
                
                if result['success']:
                    return Response({
                        'account_exists': True,
                        'account_id': result['account_id'],
                        'status': result['status'],
                        'details_submitted': result['details_submitted'],
                        'charges_enabled': result['charges_enabled'],
                        'payouts_enabled': result['payouts_enabled'],
                        'requirements': result['requirements'],
                        'message': 'Account already exists. Returning existing account information.'
                    }, status=status.HTTP_200_OK)
                else:
                    return Response({
                        'error': 'Failed to get existing account status.',
                        'details': result['errors']
                    }, status=status.HTTP_400_BAD_REQUEST)
            else:
                print("🚀 Creating new Stripe account...")
                
                # Get optional parameters for account creation
                country = request.data.get('country', 'US')
                business_type = request.data.get('business_type', 'individual')
                
                # Validate country code
                if len(country) != 2:
                    return Response({
                        'error': 'Invalid country code. Please provide a 2-letter ISO country code.'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                # Validate business type
                if business_type not in ['individual', 'company']:
                    return Response({
                        'error': 'Invalid business type. Must be "individual" or "company".'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                # Create Stripe account using the service
                result = StripeConnectService.create_stripe_account(user, country, business_type)
                
                if result['success']:
                    return Response({
                        'account_created': True,
                        'account_id': result['account_id'],
                        'status': 'incomplete',  # New accounts are always incomplete
                        'message': 'Stripe account created successfully.',
                        'next_step': 'Complete account setup using the account session.'
                    }, status=status.HTTP_201_CREATED)
                else:
                    return Response({
                        'error': 'Failed to create Stripe account.',
                        'details': result['errors']
                    }, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        logger.error(f"Unexpected error in stripe_account: {str(e)}")
        return Response({
            'error': 'Service may be unavailable. Please try again later.'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# This creates a Stripe Account Session for seller onboarding AKA get seller info to pay or edit the info
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_stripe_account_session(request):
    """
    Create a Stripe Account Session for seller onboarding.
    User must already have a Stripe account created.
    """
    try:
        user = request.user
        
        # Create account session using the service
        result = StripeConnectService.create_account_session(user)
        
        if result['success']:
            return Response({
                'message': 'Account session created successfully.',
                'client_secret': result['client_secret'],
                'account_id': result['account_id']
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'error': 'Failed to create account session.',
                'details': result['errors']
            }, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        logger.error(f"Unexpected error in create_stripe_account_session: {str(e)}")
        return Response({
            'error': 'Service may be unavailable. Please try again later.'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# Get the Stripe account status for the authenticated user
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_stripe_account_status(request):
    """
    Get the Stripe account status for the authenticated user.
    """
    try:
        user = request.user
        
        # Get account status using the service
        result = StripeConnectService.get_account_status(user)
        
        if result['success']:
            response_data = {
                'has_stripe_account': result['has_account'],
                'status': result['status']
            }
            
            # Add detailed information if account exists
            if result['has_account']:
                response_data.update({
                    'account_id': result['account_id'],
                    'details_submitted': result['details_submitted'],
                    'charges_enabled': result['charges_enabled'],
                    'payouts_enabled': result['payouts_enabled'],
                    'requirements': result['requirements']
                })
            
            return Response(response_data, status=status.HTTP_200_OK)
        else:
            return Response({
                'error': 'Failed to get account status.',
                'details': result['errors']
            }, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        logger.error(f"Unexpected error in get_stripe_account_status: {str(e)}")
        return Response({
            'error': 'Service may be unavailable. Please try again later.'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Get seller payment holds with remaining time calculation
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_seller_payment_holds(request):
    """
    Get all payment holds for the authenticated seller with remaining time calculation
    Using simplified PaymentTransaction model with integrated hold system
    """
    logger.info(f"[API] GET /stripe/holds/ called")
    
    # Debug authentication
    logger.info(f"[DEBUG] Request headers: {dict(request.headers)}")
    logger.info(f"[DEBUG] Request user: {request.user}")
    logger.info(f"[DEBUG] User authenticated: {request.user.is_authenticated}")
    
    if not request.user.is_authenticated:
        logger.warning(f"[ERROR] User not authenticated for stripe holds endpoint")
        return Response({
            'error': 'AUTHENTICATION_REQUIRED',
            'detail': 'You must be logged in to view payment holds',
            'authenticated': False
        }, status=status.HTTP_401_UNAUTHORIZED)
    
    try:
        user = request.user
        logger.info(f"[SUCCESS] Authenticated user: {user.username} (ID: {user.id})")
        
        # Get all payment transactions where the user is the seller and payment is held
        logger.info(f"[DEBUG] Querying PaymentTransaction for seller: {user.id}")
        held_transactions = PaymentTransaction.objects.filter(
            seller=user,
            status='held'
        ).select_related('order', 'buyer')
        
        logger.info(f"[INFO] Found {held_transactions.count()} held transactions for seller {user.username}")
        
        holds_data = []
        total_pending_amount = Decimal('0.00')
        
        for transaction in held_transactions:
            try:
                # Calculate remaining time using integrated hold system
                now = timezone.now()
                if transaction.planned_release_date:
                    remaining_time = transaction.planned_release_date - now
                    remaining_days = max(0, remaining_time.days)
                    remaining_hours = max(0, remaining_time.seconds // 3600)
                    
                    # Check if ready for release
                    is_ready_for_release = remaining_time.total_seconds() <= 0
                else:
                    # Use days_to_hold and hold_start_date to calculate remaining
                    remaining_days = transaction.days_remaining
                    remaining_hours = transaction.hours_remaining
                    is_ready_for_release = transaction.can_be_released
                
                # Parse item names for display (simplified from PaymentItems)
                item_list = transaction.item_names.split(', ') if transaction.item_names else []
                
                # Calculate progress percentage for UI
                total_hold_time = transaction.days_to_hold * 24  # Convert to hours
                elapsed_hours = 0
                if transaction.hold_start_date:
                    elapsed_time = now - transaction.hold_start_date
                    elapsed_hours = elapsed_time.total_seconds() / 3600
                
                progress_percentage = min(100, max(0, (elapsed_hours / total_hold_time) * 100)) if total_hold_time > 0 else 0
                
                hold_info = {
                    'transaction_id': str(transaction.id),
                    'order_id': str(transaction.order.id),
                    'buyer': {
                        'username': transaction.buyer.username,
                        'email': transaction.buyer.email,
                        'first_name': getattr(transaction.buyer, 'first_name', ''),
                        'last_name': getattr(transaction.buyer, 'last_name', '')
                    },
                    'amounts': {
                        'gross_amount': float(transaction.gross_amount),
                        'platform_fee': float(transaction.platform_fee),
                        'stripe_fee': float(transaction.stripe_fee),
                        'net_amount': float(transaction.net_amount),
                        'currency': transaction.currency
                    },
                    'order_details': {
                        'purchase_date': transaction.purchase_date.isoformat(),
                        'item_count': transaction.item_count,
                        'item_names': transaction.item_names,
                        'items': [{'product_name': name.strip(), 'quantity': 1} for name in item_list]
                    },
                    'hold_status': {
                        'reason': transaction.hold_reason,
                        'reason_display': transaction.get_hold_reason_display(),
                        'status': 'held',
                        'status_display': 'Payment on Hold',
                        'total_hold_days': transaction.days_to_hold,
                        'hold_start_date': transaction.hold_start_date.isoformat() if transaction.hold_start_date else None,
                        'planned_release_date': transaction.planned_release_date.isoformat() if transaction.planned_release_date else None,
                        'remaining_days': remaining_days,
                        'remaining_hours': remaining_hours,
                        'progress_percentage': round(progress_percentage, 1),
                        'is_ready_for_release': is_ready_for_release,
                        'hold_notes': transaction.hold_notes or f"Standard {transaction.days_to_hold}-day hold period for marketplace transactions",
                        'time_display': f"{remaining_days}d {remaining_hours}h remaining" if not is_ready_for_release else "Ready for release"
                    }
                }
                
                holds_data.append(hold_info)
                total_pending_amount += transaction.net_amount
                
            except Exception as item_error:
                logger.error(f"Error processing transaction {transaction.id}: {str(item_error)}")
                continue
        
        # Summary statistics
        summary = {
            'total_holds': len(holds_data),
            'total_pending_amount': str(total_pending_amount),
            'currency': 'USD',
            'ready_for_release_count': sum(1 for hold in holds_data if hold['hold_status']['is_ready_for_release']),
        }
        
        logger.info(f"[SUCCESS] Successfully prepared response with {len(holds_data)} holds, total pending: ${total_pending_amount}")
        
        return Response({
            'success': True,
            'summary': summary,
            'holds': holds_data,
            'message': f'Found {len(holds_data)} payment holds for seller {user.username}.',
            'debug_info': {
                'user_id': user.id,
                'username': user.username,
                'is_authenticated': True,
                'query_count': held_transactions.count()
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"[ERROR] Error retrieving seller payment holds for user {user.username}: {str(e)}")
        logger.error(f"[ERROR] Full exception: ", exc_info=True)
        return Response({
            'error': 'PAYMENT_HOLDS_RETRIEVAL_FAILED',
            'detail': f'Failed to retrieve payment holds: {str(e)}',
            'debug_info': {
                'user_id': user.id if hasattr(user, 'id') else None,
                'username': user.username if hasattr(user, 'username') else str(user),
                'is_authenticated': request.user.is_authenticated
            }
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# transfer payment to seller's connected account 
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def transfer_payment_to_seller(request):
    """
    Transfer payment to seller's connected Stripe account.
    
    Expected request body:
    {
        "transaction_id": "uuid-of-payment-transaction",
        "transfer_group": "ORDER123" (optional - will use order ID if not provided)
    }
    """
    try:
        from .stripe_service import create_transfer_to_connected_account
        
        # Get request data
        transaction_id = request.data.get('transaction_id')
        transfer_group = request.data.get('transfer_group')
        
        if not transaction_id:
            return Response({
                'error': 'MISSING_TRANSACTION_ID',
                'detail': 'Transaction ID is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get the payment transaction
        try:
            payment_transaction = PaymentTransaction.objects.select_related(
                'seller', 'buyer', 'order'
            ).get(id=transaction_id)
        except PaymentTransaction.DoesNotExist:
            return Response({
                'error': 'TRANSACTION_NOT_FOUND',
                'detail': f'Payment transaction {transaction_id} not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Security check: Only allow admins or the seller to trigger transfer
        if not (request.user.is_staff or request.user == payment_transaction.seller):
            return Response({
                'error': 'PERMISSION_DENIED',
                'detail': 'You do not have permission to transfer this payment'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # SECURITY: Only allow transfers of payments with 'held' status
        if not payment_transaction.can_transfer:
            return Response({
                'error': 'PAYMENT_NOT_TRANSFERABLE',
                'detail': f'Only payments with "held" status can be transferred. Current status: {payment_transaction.status}',
                'payment_status': payment_transaction.status,
                'transfer_allowed': False
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if seller has a connected Stripe account
        if not payment_transaction.seller.stripe_account_id:
            return Response({
                'error': 'NO_CONNECTED_ACCOUNT',
                'detail': 'Seller does not have a connected Stripe account'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if payment_transaction.planned_release_date and payment_transaction.planned_release_date > timezone.now():
            return Response({
                'error': 'TRANSFER_NOT_READY',
                'detail': f'Transfer not ready yet. Planned release date: {payment_transaction.planned_release_date.isoformat()}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Use transfer group from request or default to order ID
        if not transfer_group:
            transfer_group = f"ORDER{payment_transaction.order.id}"
        
        # Calculate transfer amount in cents
        transfer_amount_cents = int(payment_transaction.net_amount * 100)
        
        # Use currency handler to check balance and find optimal currency
        from .currency_handler import switch_currency, CurrencyHandler
        
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
            if not rate_freshness['is_fresh']:
                logger.warning(f"Exchange rate data is stale (age: {rate_freshness.get('age_hours', 'unknown')} hours)")
        except Exception as freshness_error:
            logger.warning(f"Could not check exchange rate freshness: {freshness_error}")
            rate_freshness = {'is_fresh': False, 'status': 'unknown'}
        
        currency_result = switch_currency(
            preferred_currency=payment_transaction.currency.lower(),
            required_amount_cents=transfer_amount_cents,
            destination_account_id=payment_transaction.seller.stripe_account_id
        )
        
        # Handle currency response format
        if 'success' in currency_result and 'was_converted' in currency_result:
            if currency_result['was_converted'] == True:
                # Currency conversion was needed
                logger.info(f"Currency conversion applied: {currency_result['original_currency']} to {currency_result['new_currency'].upper()} (rate: {currency_result['rate']})")
                
                # Create transfer with converted currency and amount
                transfer_result = create_transfer_to_connected_account(
                    amount=currency_result['new_amount_cents'],  # Already in cents
                    currency=currency_result['new_currency'],
                    destination_account_id=payment_transaction.seller.stripe_account_id,
                    transfer_group=transfer_group,
                    metadata={
                        'transaction_id': str(payment_transaction.id),
                        'order_id': str(payment_transaction.order.id),
                        'seller_id': str(payment_transaction.seller.id),
                        'buyer_id': str(payment_transaction.buyer.id),
                        'original_currency': currency_result['original_currency'],
                        'original_amount_cents': currency_result['original_amount_cents'],
                        'currency_conversion': True,
                        'exchange_rate': currency_result['rate'],
                    }
                )
            else:
                # No conversion needed - use original values
                logger.info(f"No currency conversion needed: using {currency_result.get('use_currency_display', payment_transaction.currency.upper())}")
                
                # Create transfer with original currency and amount
                transfer_result = create_transfer_to_connected_account(
                    amount=currency_result.get('amount_cents', transfer_amount_cents),
                    currency=currency_result.get('use_currency', payment_transaction.currency.lower()),
                    destination_account_id=payment_transaction.seller.stripe_account_id,
                    transfer_group=transfer_group,
                    metadata={
                        'transaction_id': str(payment_transaction.id),
                        'order_id': str(payment_transaction.order.id),
                        'seller_id': str(payment_transaction.seller.id),
                        'buyer_id': str(payment_transaction.buyer.id),
                        'original_currency': payment_transaction.currency.upper(),
                        'original_amount_cents': transfer_amount_cents,
                        'currency_conversion': False,
                        'exchange_rate': 1.0,
                    }
                )
            
        elif 'success' in currency_result:
            # Full response format - handle as before
            if not currency_result['success']:
                logger.error(f"Currency switch failed for transaction {transaction_id}: {currency_result.get('error')}")
                
                # Check if it's an exchange rate error
                if currency_result.get('error_type') == 'EXCHANGE_RATE_UNAVAILABLE':
                    return Response({
                        'error': 'EXCHANGE_RATE_UNAVAILABLE',
                        'detail': currency_result.get('error'),
                        'message': currency_result.get('message'),
                        'exchange_rate_status': rate_freshness,
                        'required_action': 'Update exchange rate data or contact system administrator'
                    }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
                else:
                    # Handle other currency errors (insufficient balance, etc.)
                    return Response({
                        'error': 'INSUFFICIENT_BALANCE',
                        'detail': f"Insufficient balance for transfer: {currency_result.get('error')}",
                        'balance_info': currency_result.get('balance_info', {}),
                        'available_currencies': currency_result.get('available_currencies', current_balance),
                        'current_balance_summary': {
                            'total_currencies_available': len(current_balance),
                            'highest_balance_currency': current_balance[0]['currency'] if current_balance else None,
                            'currencies_with_balance': [
                                {
                                    'currency': curr['currency'],
                                    'amount_formatted': curr['amount_formatted']
                                } 
                                for curr in current_balance[:5]  # Top 5 currencies
                            ]
                        },
                        'exchange_rate_status': rate_freshness
                    }, status=status.HTTP_400_BAD_REQUEST)
            
        else:
            # Unknown response format
            logger.error(f"Unknown currency_result format for transaction {transaction_id}: {currency_result}")
            return Response({
                'error': 'CURRENCY_HANDLER_ERROR',
                'detail': 'Unknown response format from currency handler',
                'currency_result': currency_result
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        if not transfer_result['success']:
            logger.error(f"Failed to create transfer for transaction {transaction_id}: {transfer_result['errors']}")
            return Response({
                'error': 'TRANSFER_FAILED',
                'detail': 'Failed to create transfer to seller account',
                'errors': transfer_result['errors']
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Update payment transaction status to 'processing' and store transfer_id
        transfer_started = payment_transaction.start_transfer(
            transfer_id=transfer_result['transfer_id'],
            notes=f"Transfer created by {request.user.username}: {transfer_result['transfer_id']}"
        )
        
        if not transfer_started:
            logger.error(f"Failed to update payment transaction status for {transaction_id}")
            return Response({
                'error': 'STATUS_UPDATE_FAILED',
                'detail': 'Transfer created but failed to update transaction status',
                'transfer_id': transfer_result['transfer_id']
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        logger.info(f"Payment transferred successfully: Transaction {transaction_id}, Transfer {transfer_result['transfer_id']}")
        
        # Get updated balance information after transfer
        try:
            post_transfer_balance = CurrencyHandler.get_available_currencies_with_balance()
        except Exception as balance_error:
            logger.warning(f"Could not retrieve post-transfer balance: {balance_error}")
            post_transfer_balance = current_balance
        
        # Build complete response based on currency result format
        if currency_result.get('was_converted') == True:
            # Currency conversion was performed
            logger.info(f"Building response for currency conversion scenario")
            
            response_data = {
                'success': True,
                'message': 'Transfer initiated successfully with currency conversion. Status set to processing - awaiting webhook verification.',
                'transfer_details': {
                    'transfer_id': transfer_result['transfer_id'],
                    'amount_cents': transfer_result['amount'],
                    'amount_dollars': transfer_result['amount'] / 100,
                    'currency': transfer_result['currency'],
                    'destination_account': transfer_result['destination'],
                    'transfer_group': transfer_result['transfer_group'],
                    'created_at': transfer_result['created']
                },
                'currency_info': {
                    'original_currency': currency_result['original_currency'],
                    'final_currency': currency_result['new_currency'].upper(),
                    'conversion_needed': True,
                    'exchange_rate': currency_result['rate'],
                    'original_amount_cents': currency_result['original_amount_cents'],
                    'original_amount_decimal': float(currency_result['original_amount_decimal']),
                    'final_amount_cents': currency_result['new_amount_cents'],
                    'final_amount_decimal': float(currency_result['new_amount_decimal']),
                    'conversion_summary': f"Converted {currency_result['original_amount_decimal']} {currency_result['original_currency']} to {currency_result['new_amount_decimal']} {currency_result['new_currency'].upper()} at rate {currency_result['rate']}",
                    'balance_used': {
                        'currency': currency_result['new_currency'].upper(),
                        'amount_used_cents': currency_result['new_amount_cents'],
                        'amount_used_decimal': float(currency_result['new_amount_decimal'])
                    }
                },
                'transaction_details': {
                    'transaction_id': str(payment_transaction.id),
                    'status': payment_transaction.status,
                    'net_amount': float(payment_transaction.net_amount),
                    'release_date': payment_transaction.actual_release_date.isoformat() if payment_transaction.actual_release_date else None
                },
                'balance_summary': {
                    'currencies_available_before': len(current_balance),
                    'currencies_available_after': len(post_transfer_balance),
                    'top_currencies_remaining': [
                        {
                            'currency': curr['currency'],
                            'amount_formatted': curr['amount_formatted'],
                            'amount_cents': curr['amount_cents']
                        }
                        for curr in post_transfer_balance[:3]
                    ],
                    'transfer_impact': {
                        'currency_used': currency_result['new_currency'].upper(),
                        'amount_deducted': f"{currency_result['new_amount_decimal']:.2f} {currency_result['new_currency'].upper()}"
                    }
                },
                'exchange_rate_info': {
                    'data_freshness': rate_freshness,
                    'rate_source': 'database_stored',
                    'conversion_rate': currency_result['rate'],
                    'rate_timestamp': rate_freshness.get('last_updated')
                }
            }
        else:
            # No currency conversion needed
            logger.info(f"Building response for no conversion scenario")
            
            response_data = {
                'success': True,
                'message': 'Transfer initiated successfully. Status set to processing - awaiting webhook verification.',
                'transfer_details': {
                    'transfer_id': transfer_result['transfer_id'],
                    'amount_cents': transfer_result['amount'],
                    'amount_dollars': transfer_result['amount'] / 100,
                    'currency': transfer_result['currency'],
                    'destination_account': transfer_result['destination'],
                    'transfer_group': transfer_result['transfer_group'],
                    'created_at': transfer_result['created']
                },
                'currency_info': {
                    'original_currency': payment_transaction.currency.upper(),
                    'final_currency': currency_result.get('use_currency_display', payment_transaction.currency.upper()),
                    'conversion_needed': False,
                    'exchange_rate': 1.0,
                    'original_amount_cents': transfer_amount_cents,
                    'original_amount_decimal': float(payment_transaction.net_amount),
                    'final_amount_cents': transfer_amount_cents,
                    'final_amount_decimal': float(payment_transaction.net_amount),
                    'recommendation': currency_result.get('recommendation', 'No conversion needed'),
                    'balance_used': {
                        'currency': currency_result.get('use_currency_display', payment_transaction.currency.upper()),
                        'amount_used_cents': transfer_amount_cents,
                        'amount_used_decimal': float(payment_transaction.net_amount)
                    }
                },
                'transaction_details': {
                    'transaction_id': str(payment_transaction.id),
                    'status': payment_transaction.status,
                    'net_amount': float(payment_transaction.net_amount),
                    'release_date': payment_transaction.actual_release_date.isoformat() if payment_transaction.actual_release_date else None
                },
                'balance_summary': {
                    'currencies_available_before': len(current_balance),
                    'currencies_available_after': len(post_transfer_balance),
                    'top_currencies_remaining': [
                        {
                            'currency': curr['currency'],
                            'amount_formatted': curr['amount_formatted'],
                            'amount_cents': curr['amount_cents']
                        }
                        for curr in post_transfer_balance[:3]
                    ],
                    'transfer_impact': {
                        'currency_used': currency_result.get('use_currency_display', payment_transaction.currency.upper()),
                        'amount_deducted': f"{payment_transaction.net_amount:.2f} {currency_result.get('use_currency_display', payment_transaction.currency.upper())}"
                    }
                },
                'exchange_rate_info': {
                    'data_freshness': rate_freshness,
                    'rate_source': 'database_stored',
                    'fallback_used': currency_result.get('fallback_rates_used', False)
                }
            }
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Unexpected error in transfer_payment_to_seller: {str(e)}", exc_info=True)
        return Response({
            'error': 'TRANSFER_ERROR',
            'detail': f'An unexpected error occurred: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def seller_payout(request):
    """
    Simple Stripe payout creation - just create the payout with Stripe API.
    
    Expected request data:
    {
        "amount": 24784,  # Amount in cents
        "currency": "eur",  # Currency code
        "description": "Monthly payout"  # optional
    }
    """
    print("🔍 === SIMPLE SELLER_PAYOUT API CALLED ===")
    print(f"👤 User: {request.user.username} (ID: {request.user.id})")
    print(f"🔐 Is authenticated: {request.user.is_authenticated}")
    print(f"📊 Request data: {request.data}")
    
    try:
        # Get current user info
        user = request.user
        
        print(f"🔧 User ID: {user.id}")
        
        # Verify user has Stripe account
        stripe_account_id = user.stripe_account_id

        if not stripe_account_id:
            print("⚠️ User does not have a Stripe account.")
            return Response({
                'error': 'NO_STRIPE_ACCOUNT',
                'detail': 'User does not have a connected Stripe account.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        
        StripeAccountBalance = stripe.Balance.retrieve(
            stripe_account=stripe_account_id,
            expand=['available']
        )
        available_balance = StripeAccountBalance['available']


        print(f"🔧 Available balance: {available_balance}")


        if not available_balance or len(available_balance) == 0:
            print("⚠️ No available balance found for this account.")
            return Response({
                'error': 'NO_AVAILABLE_BALANCE',
                'detail': 'No available balance found for this Stripe account.'
            }, status=status.HTTP_400_BAD_REQUEST)
        

        """[<Available at 0x2973e8f39f0> JSON: {
  "amount": 223723,
  "currency": "eur",
  "source_types": {
    "card": 223723
  }
}]"""
        
        # Get the first available balance (usually EUR or primary currency)
        first_balance = available_balance[0]
        payout_amount = first_balance['amount']
        payout_currency = first_balance['currency']
        
        print(f"💰 Using balance: {payout_amount} {payout_currency.upper()}")
        print(f"💰 Amount in cents: {payout_amount}")
        print(f"💰 Amount formatted: €{payout_amount/100:.2f}")
        
        if payout_amount <= 1:
            print("⚠️ Available balance is zero or negative.")
            return Response({
                'error': 'INSUFFICIENT_BALANCE',
                'detail': f'Available balance is {payout_amount} cents. Cannot create payout.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create Stripe payout using actual available balance
        stripe_payout = stripe.Payout.create(
            amount=payout_amount,  # Use actual available balance amount
            currency=payout_currency,  # Use actual available balance currency
            stripe_account=stripe_account_id,
            method="instant",
            metadata={
                'user_id': str(user.id),
                'original_amount': payout_amount,
                'payout_currency': payout_currency,
            }
        )
        
        print(f"✅ Stripe payout created: {stripe_payout.id}")
        print(f"📊 Payout status: {stripe_payout.status}")
        
        # Simple response with actual payout amounts
        response_data = {
            'success': True,
            'payout': {
                'stripe_payout_id': stripe_payout.id,
                'status': stripe_payout.status,
                'amount_cents': payout_amount,
                'amount_formatted': f"€{payout_amount/100:.2f}",
                'currency': payout_currency,
                'created': stripe_payout.created
            },
            'user': {
                'id': str(user.id),
                'username': user.username,
                'stripe_account_id': stripe_account_id
            },
            'message': f'Payout of €{payout_amount/100:.2f} created successfully using available balance'
        }
        
        logger.info(f"Simple payout created successfully: {stripe_payout.id} for user {user.id}")
        
        return Response(response_data, status=status.HTTP_201_CREATED)
        
    except stripe.error.StripeError as e:
        logger.error(f"Stripe payout failed: {e}")
        return Response({
            'error': 'STRIPE_PAYOUT_FAILED',
            'detail': str(e),
            'stripe_error_code': getattr(e, 'code', 'unknown')
        }, status=status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        logger.error(f"Unexpected error in seller_payout: {str(e)}", exc_info=True)
        return Response({
            'error': 'PAYOUT_ERROR',
            'detail': f'An unexpected error occurred: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


