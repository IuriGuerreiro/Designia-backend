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
from .models import PaymentTracker, WebhookEvent, PaymentTransaction, PaymentHold, PaymentItem
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
            
    else:
        print(f"ℹ️ Unhandled event type: {event.type}")

    return HttpResponse(status=200, content='Webhook received and processed successfully.')

# Create PaymentTransaction records for each seller in the order
def create_payment_transactions(order, session):
    """
    Create PaymentTransaction records for each seller in the order
    This tracks payments per seller with holding periods
    """
    from .models import PaymentTransaction, PaymentHold, PaymentItem
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
            
            # Create PaymentTransaction
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
                metadata={
                    'order_id': str(order.id),
                    'stripe_session_id': stripe_checkout_session_id,
                    'seller_id': str(seller.id),
                    'buyer_id': str(order.buyer.id)
                }
            )
            
            print(f"✅ Created payment transaction {payment_transaction.id} for ${net_amount}")
            
            # Create PaymentItems for detailed tracking
            for order_item in seller_data['items']:
                PaymentItem.objects.create(
                    payment_transaction=payment_transaction,
                    product=order_item.product,
                    order_item=order_item,
                    quantity=order_item.quantity,
                    unit_price=order_item.unit_price,
                    total_price=order_item.total_price,
                    product_name=order_item.product_name,
                    product_sku=getattr(order_item.product, 'sku', '')
                )
            
            # Fixed hold period for all purchases
            hold_days = 7  # Fixed 7-day hold period
            hold_reason = 'standard'  # Standard hold for all purchases
            
            # Calculate planned release date
            planned_release_date = timezone.now() + timezone.timedelta(days=hold_days)
            
            # Create PaymentHold
            payment_hold = PaymentHold.objects.create(
                payment_transaction=payment_transaction,
                reason=hold_reason,
                hold_days=hold_days,
                planned_release_date=planned_release_date,
                hold_notes=f"Automatic hold for {hold_reason} - {hold_days} days"
            )
            
            print(f"🔒 Created payment hold for {hold_days} days (reason: {hold_reason})")
        
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
        ).select_related('payment_hold', 'order', 'buyer').prefetch_related('payment_items')
        
        logger.info(f"[INFO] Found {held_transactions.count()} held transactions for seller {user.username}")
        
        holds_data = []
        total_pending_amount = Decimal('0.00')
        
        for transaction in held_transactions:
            try:
                # Get the payment hold information
                payment_hold = transaction.payment_hold
                
                # Calculate remaining time
                now = timezone.now()
                if payment_hold.planned_release_date:
                    remaining_time = payment_hold.planned_release_date - now
                    remaining_days = max(0, remaining_time.days)
                    remaining_hours = max(0, remaining_time.seconds // 3600)
                    
                    # Check if ready for release
                    is_ready_for_release = remaining_time.total_seconds() <= 0
                else:
                    remaining_days = 30  # Default if no planned date
                    remaining_hours = 0
                    is_ready_for_release = False
                
                # Get order items for this seller
                seller_items = transaction.payment_items.all()
                item_details = []
                for item in seller_items:
                    item_details.append({
                        'product_name': item.product_name,
                        'quantity': item.quantity,
                        'unit_price': str(item.unit_price),
                        'total_price': str(item.total_price)
                    })
                
                hold_info = {
                    'transaction_id': str(transaction.id),
                    'order_id': str(transaction.order.id),
                    'buyer_username': transaction.buyer.username,
                    'buyer_email': transaction.buyer.email,
                    'gross_amount': str(transaction.gross_amount),
                    'platform_fee': str(transaction.platform_fee),
                    'stripe_fee': str(transaction.stripe_fee),
                    'net_amount': str(transaction.net_amount),
                    'currency': transaction.currency,
                    'purchase_date': transaction.purchase_date.isoformat(),
                    'item_count': transaction.item_count,
                    'item_names': transaction.item_names,
                    'items': item_details,
                    'hold': {
                        'reason': payment_hold.reason,
                        'reason_display': payment_hold.get_reason_display(),
                        'status': payment_hold.status,
                        'status_display': payment_hold.get_status_display(),
                        'hold_days': payment_hold.hold_days,
                        'hold_start_date': payment_hold.hold_start_date.isoformat(),
                        'planned_release_date': payment_hold.planned_release_date.isoformat() if payment_hold.planned_release_date else None,
                        'remaining_days': remaining_days,
                        'remaining_hours': remaining_hours,
                        'is_ready_for_release': is_ready_for_release,
                        'hold_notes': payment_hold.hold_notes,
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
            'ready_for_release_count': sum(1 for hold in holds_data if hold['hold']['is_ready_for_release']),
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

