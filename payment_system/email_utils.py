import os
import logging
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from marketplace.models import Order
from authentication.models import EmailRequestAttempt
from authentication.utils import get_client_ip

logger = logging.getLogger(__name__)


def get_email_rate_limit_status_for_receipts(user, email, request_type='order_receipt'):
    """
    Check rate limit status for order receipt emails
    Returns (can_send, time_remaining_seconds)
    """
    # Check for recent receipt email attempts (within last 5 minutes)
    five_minutes_ago = timezone.now() - timedelta(minutes=5)
    
    recent_attempts = EmailRequestAttempt.objects.filter(
        user=user,
        request_type=request_type,
        created_at__gte=five_minutes_ago
    )
    
    if recent_attempts.exists():
        # Calculate time remaining
        latest_attempt = recent_attempts.order_by('-created_at').first()
        time_since_last = timezone.now() - latest_attempt.created_at
        time_remaining = timedelta(minutes=5) - time_since_last
        time_remaining_seconds = int(time_remaining.total_seconds())
        
        return False, max(0, time_remaining_seconds)
    
    return True, 0


def record_email_attempt_for_receipts(user, email, request_type='order_receipt', request=None):
    """Record an order receipt email attempt for rate limiting"""
    ip_address = get_client_ip(request) if request else None
    
    EmailRequestAttempt.objects.create(
        user=user,
        email=email,
        request_type=request_type,
        ip_address=ip_address
    )


def send_order_receipt_email(order, request=None):
    """
    Send order receipt email to customer
    Similar to 2FA email implementation but for order receipts
    """
    try:
        user = order.buyer
        
        # Check rate limit to prevent spam
        can_send, time_remaining = get_email_rate_limit_status_for_receipts(user, user.email)
        if not can_send:
            logger.warning(f"Rate limit exceeded for receipt email to {user.email}. Time remaining: {time_remaining}s")
            return False, f"Rate limit exceeded. Please wait {time_remaining} seconds before requesting another receipt."
        
        # Record the attempt
        record_email_attempt_for_receipts(user, user.email, 'order_receipt', request)
        
        # Get frontend URL for links in email
        frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:5173')
        
        # Prepare email context
        context = {
            'order': order,
            'user': user,
            'frontend_url': frontend_url,
            'support_email': 'support@designia.com',
            'company_name': 'Designia',
        }
        
        # Render email templates
        html_content = render_to_string('payment_system/emails/order_receipt.html', context)
        text_content = render_to_string('payment_system/emails/order_receipt.txt', context)
        
        # Email details
        subject = f"Order Receipt #{str(order.id)[:8]} - Designia"
        from_email = settings.DEFAULT_FROM_EMAIL
        to_email = [user.email]
        
        # Check if we're in development mode (console backend)
        if settings.EMAIL_BACKEND == 'django.core.mail.backends.console.EmailBackend':
            # Print to console for development
            print("\n" + "="*80)
            print("📧 ORDER RECEIPT EMAIL")
            print("="*80)
            print(f"📧 To: {user.email}")
            print(f"👤 Customer: {user.first_name or user.username}")
            print(f"🛒 Order: #{str(order.id)[:8]}")
            print(f"💰 Total: ${order.total_amount}")
            print(f"📦 Items: {order.items.count()}")
            print(f"📅 Date: {order.created_at}")
            print(f"📋 Subject: {subject}")
            print("-" * 80)
            print("📄 EMAIL CONTENT (TEXT VERSION):")
            print("-" * 80)
            print(text_content)
            print("="*80)
            print("  Order receipt printed to console (development mode)")
            print("🔗 HTML version would be sent in production")
            print("="*80 + "\n")
            
            return True, "Order receipt email sent successfully (development mode)"
        
        else:
            # Send actual email in production
            try:
                # Create email message with both HTML and text versions
                email_message = EmailMultiAlternatives(
                    subject=subject,
                    body=text_content,  # Plain text version
                    from_email=from_email,
                    to=to_email,
                )
                
                # Attach HTML version
                email_message.attach_alternative(html_content, "text/html")
                
                # Send the email
                email_message.send()
                
                logger.info(f"Order receipt email sent successfully to {user.email} for order {order.id}")
                return True, "Order receipt email sent successfully"
                
            except Exception as email_error:
                logger.error(f"Failed to send order receipt email to {user.email}: {str(email_error)}")
                return False, f"Failed to send receipt email: {str(email_error)}"
    
    except Exception as e:
        logger.error(f"Error in send_order_receipt_email: {str(e)}")
        return False, f"Error sending receipt email: {str(e)}"


def send_order_status_update_email(order, previous_status, new_status, request=None):
    """
    Send order status update email to customer
    For important status changes like shipped, delivered, cancelled
    """
    try:
        user = order.buyer
        
        # Only send emails for important status changes
        important_statuses = ['shipped', 'delivered', 'cancelled', 'refunded']
        if new_status not in important_statuses:
            return True, "Status update email not required for this status"
        
        # Check rate limit
        can_send, time_remaining = get_email_rate_limit_status_for_receipts(user, user.email, 'order_status_update')
        if not can_send:
            logger.warning(f"Rate limit exceeded for status update email to {user.email}")
            return False, f"Rate limit exceeded for status updates"
        
        # Record the attempt
        record_email_attempt_for_receipts(user, user.email, 'order_status_update', request)
        
        # Get frontend URL
        frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:5173')
        
        # Prepare status-specific content
        status_messages = {
            'shipped': {
                'emoji': '🚚',
                'title': 'Your Order Has Been Shipped!',
                'message': 'Great news! Your order is on its way to you.',
            },
            'delivered': {
                'emoji': '📦',
                'title': 'Your Order Has Been Delivered!',
                'message': 'Your order has been successfully delivered. We hope you love your purchase!',
            },
            'cancelled': {
                'emoji': '❌',
                'title': 'Your Order Has Been Cancelled',
                'message': 'Your order has been cancelled. If you had paid, a refund will be processed.',
            },
            'refunded': {
                'emoji': '💰',
                'title': 'Your Order Has Been Refunded',
                'message': 'Your refund has been processed and should appear in your account soon.',
            }
        }
        
        status_info = status_messages.get(new_status, {
            'emoji': '📋',
            'title': f'Order Status Updated',
            'message': f'Your order status has been updated to {new_status.replace("_", " ").title()}.',
        })
        
        # Subject line
        subject = f"{status_info['emoji']} {status_info['title']} - Order #{str(order.id)[:8]}"
        
        # Check if we're in development mode
        if settings.EMAIL_BACKEND == 'django.core.mail.backends.console.EmailBackend':
            print("\n" + "="*80)
            print("📧 ORDER STATUS UPDATE EMAIL")
            print("="*80)
            print(f"📧 To: {user.email}")
            print(f"👤 Customer: {user.first_name or user.username}")
            print(f"🛒 Order: #{str(order.id)[:8]}")
            print(f"📋 Status Change: {previous_status} → {new_status}")
            print(f"📅 Updated: {timezone.now()}")
            print(f"📋 Subject: {subject}")
            print("-" * 80)
            print(f"{status_info['emoji']} {status_info['title']}")
            print(f"{status_info['message']}")
            print(f"\nTrack your order: {frontend_url}/my-orders/{order.id}")
            print("="*80)
            print("  Status update email printed to console (development mode)")
            print("="*80 + "\n")
            
            return True, "Status update email sent successfully (development mode)"
        
        else:
            # Send actual email in production
            # You could create specific templates for status updates, but for now using simple text
            text_content = f"""
Hello {user.first_name or user.username},

{status_info['emoji']} {status_info['title']}

{status_info['message']}

Order Details:
- Order Number: #{str(order.id)[:8]}
- Total: ${order.total_amount}
- Status: {new_status.replace('_', ' ').title()}

Track your order: {frontend_url}/my-orders/{order.id}

Best regards,
The Designia Team

---
This is an automated message. For support, contact us at support@designia.com
            """
            
            try:
                from django.core.mail import send_mail
                
                send_mail(
                    subject=subject,
                    message=text_content,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=False,
                )
                
                logger.info(f"Status update email sent to {user.email} for order {order.id} ({previous_status} → {new_status})")
                return True, "Status update email sent successfully"
                
            except Exception as email_error:
                logger.error(f"Failed to send status update email: {str(email_error)}")
                return False, f"Failed to send status update email: {str(email_error)}"
    
    except Exception as e:
        logger.error(f"Error in send_order_status_update_email: {str(e)}")
        return False, f"Error sending status update email: {str(e)}"


def send_order_cancellation_receipt_email(order, cancellation_reason, refund_amount=None, request=None):
    """
    Send order cancellation receipt email to customer
    Specific email for when orders are cancelled with refunds
    """
    try:
        user = order.buyer
        
        # Check rate limit
        can_send, time_remaining = get_email_rate_limit_status_for_receipts(user, user.email, 'order_cancellation')
        if not can_send:
            logger.warning(f"Rate limit exceeded for cancellation email to {user.email}")
            return False, f"Rate limit exceeded for cancellation emails"
        
        # Record the attempt
        record_email_attempt_for_receipts(user, user.email, 'order_cancellation', request)
        
        # Get frontend URL
        frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:5173')
        
        # Subject line
        subject = f" Order Cancelled - #{str(order.id)[:8]} | Refund Processing"
        
        # Check if we're in development mode
        if settings.EMAIL_BACKEND == 'django.core.mail.backends.console.EmailBackend':
            print("\n" + "="*80)
            print("📧 ORDER CANCELLATION EMAIL")
            print("="*80)
            print(f"📧 To: {user.email}")
            print(f"👤 Customer: {user.first_name or user.username}")
            print(f"🛒 Order: #{str(order.id)[:8]}")
            print(f"💰 Original Total: ${order.total_amount}")
            if refund_amount:
                print(f"💸 Refund Amount: ${refund_amount}")
            print(f"📋 Cancellation Reason: {cancellation_reason}")
            print(f"📅 Cancelled: {order.cancelled_at or timezone.now()}")
            print(f"📋 Subject: {subject}")
            print("-" * 80)
            print(" ORDER CANCELLATION CONFIRMATION")
            print(f"Your order has been successfully cancelled.")
            if refund_amount:
                print(f"A refund of ${refund_amount} has been processed and will appear in your account within 5-10 business days.")
            print(f"\nReason: {cancellation_reason}")
            print(f"\nView order details: {frontend_url}/my-orders/{order.id}")
            print("="*80)
            print("  Cancellation email printed to console (development mode)")
            print("="*80 + "\n")
            
            return True, "Cancellation email sent successfully (development mode)"
        
        else:
            # Send actual email in production
            refund_text = f"\n\nREFUND INFORMATION:\nA refund of ${refund_amount} has been processed and will appear in your account within 5-10 business days." if refund_amount else ""
            
            text_content = f"""
Hello {user.first_name or user.username},

Your order has been successfully cancelled.

ORDER DETAILS:
- Order Number: #{str(order.id)[:8]}
- Original Total: ${order.total_amount}
- Cancellation Reason: {cancellation_reason}
- Cancelled At: {order.cancelled_at or timezone.now()}
{refund_text}

If you have any questions about this cancellation, please contact our support team.

View order details: {frontend_url}/my-orders/{order.id}

Best regards,
The Designia Team

---
This is an automated message. For support, contact us at support@designia.com
            """
            
            try:
                from django.core.mail import send_mail
                
                send_mail(
                    subject=subject,
                    message=text_content,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=False,
                )
                
                logger.info(f"Cancellation email sent to {user.email} for order {order.id}")
                return True, "Cancellation email sent successfully"
                
            except Exception as email_error:
                logger.error(f"Failed to send cancellation email: {str(email_error)}")
                return False, f"Failed to send cancellation email: {str(email_error)}"
    
    except Exception as e:
        logger.error(f"Error in send_order_cancellation_receipt_email: {str(e)}")
        return False, f"Error sending cancellation email: {str(e)}"


def send_failed_refund_notification_email(order, failure_reason, refund_amount=None, request=None):
    """
    Send failed refund notification email to customer
    Notifies customer that refund failed and they need to contact support
    """
    try:
        user = order.buyer
        
        # Check rate limit
        can_send, time_remaining = get_email_rate_limit_status_for_receipts(user, user.email, 'failed_refund_notification')
        if not can_send:
            logger.warning(f"Rate limit exceeded for failed refund notification email to {user.email}")
            return False, f"Rate limit exceeded for failed refund notifications"
        
        # Record the attempt
        record_email_attempt_for_receipts(user, user.email, 'failed_refund_notification', request)
        
        # Get frontend URL
        frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:5173')
        support_email = os.getenv('SUPPORT_EMAIL', 'support@designia.com')
        
        # Subject line
        subject = f" Refund Processing Failed - Order #{str(order.id)[:8]} - Action Required"
        
        # Check if we're in development mode
        if settings.EMAIL_BACKEND == 'django.core.mail.backends.console.EmailBackend':
            print("\n" + "="*80)
            print("📧 FAILED REFUND NOTIFICATION EMAIL")
            print("="*80)
            print(f"📧 To: {user.email}")
            print(f"👤 Customer: {user.first_name or user.username}")
            print(f"🛒 Order: #{str(order.id)[:8]}")
            print(f" Failure Reason: {failure_reason}")
            print(f"💰 Refund Amount: ${refund_amount}" if refund_amount else "💰 Refund Amount: Not specified")
            print(f"📅 Failed: {timezone.now()}")
            print(f"📋 Subject: {subject}")
            print("-" * 80)
            print(" REFUND PROCESSING FAILED")
            print(f"Unfortunately, we were unable to process your refund automatically.")
            print(f"Reason: {failure_reason}")
            print()
            print("📞 NEXT STEPS:")
            print("• Contact our support team immediately")
            print(f"• Email: {support_email}")
            print(f"• Reference Order Number: #{str(order.id)[:8]}")
            print("• We will arrange an alternative refund method (bank transfer, etc.)")
            print(f"\nView order details: {frontend_url}/my-orders/{order.id}")
            print("="*80)
            print("  Failed refund notification email printed to console (development mode)")
            print("="*80 + "\n")
            
            return True, "Failed refund notification email sent successfully (development mode)"
        
        else:
            # Send actual email in production
            text_content = f"""
Hello {user.first_name or user.username},

 REFUND PROCESSING FAILED

We apologize, but we encountered an issue processing your refund for Order #{str(order.id)[:8]}.

Issue Details:
- Order Number: #{str(order.id)[:8]}
- Order Total: ${order.total_amount}
- Refund Amount: ${refund_amount or order.total_amount}
- Failure Reason: {failure_reason}
- Date: {timezone.now().strftime('%B %d, %Y at %I:%M %p')}

📞 IMMEDIATE ACTION REQUIRED

Please contact our support team to arrange an alternative refund method:

• Email: {support_email}
• Reference your Order Number: #{str(order.id)[:8]}
• Your account email: {user.email}

We will process your refund via bank transfer or another secure method. Our support team will respond within 24 hours to resolve this issue.

Order Details:
View your order: {frontend_url}/my-orders/{order.id}

We sincerely apologize for the inconvenience and will ensure your refund is processed promptly through alternative means.

Best regards,
The Designia Team

---
This is an automated message regarding a failed refund processing.
For immediate assistance, contact us at {support_email}
            """
            
            try:
                from django.core.mail import send_mail
                
                send_mail(
                    subject=subject,
                    message=text_content,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=False,
                )
                
                logger.info(f"Failed refund notification email sent to {user.email} for order {order.id}")
                return True, "Failed refund notification email sent successfully"
                
            except Exception as email_error:
                logger.error(f"Failed to send failed refund notification email: {str(email_error)}")
                return False, f"Failed to send failed refund notification email: {str(email_error)}"
    
    except Exception as e:
        logger.error(f"Error in send_failed_refund_notification_email: {str(e)}")
        return False, f"Error sending failed refund notification email: {str(e)}"