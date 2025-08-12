import os
import stripe
import json
import logging
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
from .models import PaymentTracker, WebhookEvent
from .serializers import PaymentTrackerSerializer, WebhookEventSerializer

# Set the Stripe API key from Django settings
stripe.api_key = settings.STRIPE_SECRET_KEY

# Add a check to ensure the key is loaded
if not stripe.api_key:
    raise ValueError("Stripe API key not found. Please set STRIPE_SECRET_KEY in your Django settings.")

# Initialize logger
logger = logging.getLogger(__name__)

User = get_user_model()


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def payment_tracker_list(request):
    """List payment trackers for the authenticated user"""
    trackers = PaymentTracker.objects.filter(user=request.user)
    serializer = PaymentTrackerSerializer(trackers, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def payment_tracker_detail(request, tracker_id):
    """Get details of a specific payment tracker"""
    try:
        tracker = PaymentTracker.objects.get(id=tracker_id, user=request.user)
        serializer = PaymentTrackerSerializer(tracker)
        return Response(serializer.data)
    except PaymentTracker.DoesNotExist:
        return Response(
            {'error': 'Payment tracker not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_payment_tracker(request):
    """Create a new payment tracker entry"""
    data = request.data
    
    try:
        order = Order.objects.get(id=data['order_id'], user=request.user)
        
        tracker = PaymentTracker.objects.create(
            stripe_payment_intent_id=data.get('stripe_payment_intent_id', ''),
            stripe_refund_id=data.get('stripe_refund_id', ''),
            order=order,
            user=request.user,
            transaction_type=data.get('transaction_type', 'payment'),
            status=data.get('status', 'pending'),
            amount=Decimal(data['amount']),
            currency=data.get('currency', 'USD'),
            notes=data.get('notes', '')
        )
        
        serializer = PaymentTrackerSerializer(tracker)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
        
    except Order.DoesNotExist:
        return Response(
            {'error': 'Order not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except KeyError as e:
        return Response(
            {'error': f'Missing required field: {str(e)}'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        logger.error(f"Error creating payment tracker: {str(e)}")
        return Response(
            {'error': 'Internal server error'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


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

    print(f"🔔 Raw webhook body: {request.body}")
    print(f"🔔 Headers: {request.headers}")
    
    try:
        event = stripe.Event.construct_from(
            json.loads(payload), stripe.api_key
        )
        print(f"🔔 Event constructed successfully: {event.type}")
        print(f"🔔 Event data object: {type(event.data.object)}")
        print(f"🔔 Event data object dict: {event.data}")
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
    else:
        print(f"ℹ️ Unhandled event type: {event.type}")

    return HttpResponse(status=200, content='Webhook received and processed successfully.')


@api_view(['GET'])
def webhook_events_list(request):
    """List recent webhook events (admin only)"""
    if not request.user.is_staff:
        return Response(
            {'error': 'Permission denied'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    events = WebhookEvent.objects.all()[:50]  # Last 50 events
    serializer = WebhookEventSerializer(events, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_payment_summary(request):
    """Get payment summary for the authenticated user"""
    trackers = PaymentTracker.objects.filter(user=request.user)
    
    summary = {
        'total_payments': trackers.filter(transaction_type='payment').count(),
        'total_refunds': trackers.filter(transaction_type__in=['refund', 'partial_refund']).count(),
        'succeeded_payments': trackers.filter(transaction_type='payment', status='succeeded').count(),
        'failed_payments': trackers.filter(transaction_type='payment', status='failed').count(),
        'total_amount': sum(
            tracker.amount for tracker in trackers.filter(transaction_type='payment', status='succeeded')
        ),
        'refunded_amount': sum(
            tracker.amount for tracker in trackers.filter(transaction_type__in=['refund', 'partial_refund'])
        )
    }
    
    return Response(summary)


def handle_successful_payment(session):
    """
    Handle successful payment by creating order and clearing cart
    """
    print("🔔 Handling successful payment...")
    print(f"Session ID: {session.get('id', 'Unknown')}")
    print(f"Session data keys: {list(session.keys()) if isinstance(session, dict) else 'Not a dict'}")
    
    try:
        with transaction.atomic():
            # Extract user_id from metadata
            user_id = session['metadata'].get('user_id')
            
            if not user_id:
                print(f"❌ Missing user_id in session metadata")
                return False
                
            # Get user and their cart
            User = get_user_model()
            try:
                user = User.objects.get(id=user_id)
                cart = Cart.get_or_create_cart(user=user)
            except User.DoesNotExist as e:
                print(f"❌ User not found: {e}")
                return False
                
            # Check if cart has items
            cart_items = cart.items.all()
            if not cart_items.exists():
                print(f"❌ User cart is empty")
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
                
            # Calculate totals from cart
            subtotal = sum(item.total_price for item in cart_items)
            shipping_cost = Decimal('19.99')  # Fixed shipping for now
            tax_amount = Decimal(session.get('total_details', {}).get('amount_tax', 0)) / 100  # Convert from cents
            total_amount = Decimal(session['amount_total']) / 100  # Convert from cents
            
            # Create the order with payment_confirmed status
            order = Order.objects.create(
                buyer=user,
                status='payment_confirmed',  # Set status as payment_confirmed (set by Stripe webhook)
                payment_status='paid',  # Set payment status as paid
                subtotal=subtotal,
                shipping_cost=shipping_cost,
                tax_amount=tax_amount,
                total_amount=total_amount,
                shipping_address=shipping_address,
                is_locked=True,
            )
            
            print(f"📦 Order {order.id} created with status 'payment_confirmed' and payment_status 'paid'")
            
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
                
                # Update product stock
                if product.stock_quantity >= cart_item.quantity:
                    product.stock_quantity -= cart_item.quantity
                    product.save(update_fields=['stock_quantity'])
                else:
                    print(f"⚠️ Warning: Insufficient stock for product {product.name}")
                    
            print(f"✅ Order {order.id} created successfully with {cart_items.count()} items")
            
            # Clear all cart items after successful order creation
            cart.clear_items()
            print(f"🛒 Cart cleared for user {user.username}")
            
            return True
            
    except Exception as e:
        print(f"❌ Error handling successful payment: {str(e)}")
        return False


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
        
        print(f"🔔 Creating Stripe checkout session for user {request.user.id}")
        # Create Stripe Embedded Checkout Session
        session = stripe.checkout.Session.create(
            ui_mode='embedded',
            line_items=line_items,
            mode='payment',
            return_url=f"http://localhost:5173/order-success/",
            metadata={
                "user_id":str(request.user.id),
                "cart_id":str(cart.id), 
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

            # Update order status to cancelled
            order.status = 'cancelled'
            order.payment_status = 'refunded' if refund_processed else order.payment_status
            order.cancellation_reason = cancellation_reason
            order.cancelled_by = request.user
            order.cancelled_at = timezone.now()
            order.save()

            # Restore stock for cancelled items
            for item in order.items.all():
                product = item.product
                product.stock_quantity += item.quantity
                product.save(update_fields=['stock_quantity'])
                logger.info(f"Restored {item.quantity} units to product {product.name}")

            # Log the cancellation
            logger.info(f"Order {order.id} cancelled by user {request.user.username}. Refund processed: {refund_processed}")

            return Response({
                'success': True,
                'message': 'Order cancelled successfully',
                'refund_processed': refund_processed,
                'refund_amount': str(refund_amount) if refund_processed else None,
                'stripe_refund_id': stripe_refund_id,
                'order': {
                    'id': str(order.id),
                    'status': order.status,
                    'payment_status': order.payment_status,
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


# Health check endpoint
@api_view(['GET'])
def health_check(request):
    """Simple health check endpoint"""
    return Response({
        'status': 'ok',
        'timestamp': timezone.now(),
        'payment_system': 'operational'
    })
