"""
Django management command to test order receipt email functionality
Usage: python manage.py test_receipt_email [order_id]
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from marketplace.models import Order
from payment_system.email_utils import send_order_receipt_email, send_order_status_update_email, send_order_cancellation_receipt_email

User = get_user_model()


class Command(BaseCommand):
    help = 'Test order receipt email functionality'

    def add_arguments(self, parser):
        parser.add_argument(
            'order_id',
            nargs='?',
            type=str,
            help='Order ID to send receipt for (optional - will use latest order if not provided)'
        )
        parser.add_argument(
            '--type',
            type=str,
            choices=['receipt', 'status_update', 'cancellation'],
            default='receipt',
            help='Type of email to send (default: receipt)'
        )
        parser.add_argument(
            '--new-status',
            type=str,
            help='New status for status update emails (e.g., shipped, delivered)'
        )
        parser.add_argument(
            '--reason',
            type=str,
            default='Testing cancellation email',
            help='Cancellation reason for cancellation emails'
        )

    def handle(self, *args, **options):
        try:
            # Get the order
            if options['order_id']:
                try:
                    order = Order.objects.get(id=options['order_id'])
                    self.stdout.write(f"Using specified order: {order.id}")
                except Order.DoesNotExist:
                    raise CommandError(f"Order with ID {options['order_id']} does not exist")
            else:
                # Get the latest order
                order = Order.objects.filter(payment_status='paid').order_by('-created_at').first()
                if not order:
                    raise CommandError("No paid orders found in the database")
                self.stdout.write(f"Using latest paid order: {order.id}")

            # Display order info
            self.stdout.write(self.style.SUCCESS(f"\n📦 Order Information:"))
            self.stdout.write(f"   Order ID: {order.id}")
            self.stdout.write(f"   Customer: {order.buyer.email}")
            self.stdout.write(f"   Status: {order.status}")
            self.stdout.write(f"   Payment Status: {order.payment_status}")
            self.stdout.write(f"   Total: ${order.total_amount}")
            self.stdout.write(f"   Items: {order.items.count()}")
            self.stdout.write(f"   Created: {order.created_at}")

            # Send the appropriate email
            email_type = options['type']
            
            if email_type == 'receipt':
                self.stdout.write(f"\n📧 Sending order receipt email...")
                success, message = send_order_receipt_email(order)
                
            elif email_type == 'status_update':
                new_status = options.get('new_status', 'shipped')
                previous_status = order.status
                self.stdout.write(f"\n📧 Sending status update email ({previous_status} → {new_status})...")
                success, message = send_order_status_update_email(order, previous_status, new_status)
                
            elif email_type == 'cancellation':
                reason = options.get('reason', 'Testing cancellation email')
                refund_amount = str(order.total_amount)
                self.stdout.write(f"\n📧 Sending cancellation email...")
                success, message = send_order_cancellation_receipt_email(order, reason, refund_amount)

            # Display result
            if success:
                self.stdout.write(self.style.SUCCESS(f"\n✅ Email sent successfully!"))
                self.stdout.write(f"   Message: {message}")
                self.stdout.write(f"   To: {order.buyer.email}")
                
                if email_type == 'receipt':
                    self.stdout.write(f"\n💡 Tips:")
                    self.stdout.write(f"   • Check console output above for the email content")
                    self.stdout.write(f"   • In production, this would be sent as HTML email")
                    self.stdout.write(f"   • Rate limiting is active (5 min cooldown for receipts)")
                    
            else:
                self.stdout.write(self.style.ERROR(f"\n❌ Failed to send email:"))
                self.stdout.write(f"   Error: {message}")

            # Show next steps
            from django.conf import settings
            self.stdout.write(f"\n🔧 Development Notes:")
            self.stdout.write(f"   • Email backend: {settings.EMAIL_BACKEND}")
            self.stdout.write(f"   • Templates: payment_system/templates/payment_system/emails/")
            self.stdout.write(f"   • Email utils: payment_system/email_utils.py")
            self.stdout.write(f"   • Rate limiting: 5 minutes for receipts, 1 minute for other types")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n❌ Command failed: {str(e)}"))
            raise CommandError(f"Failed to test email: {str(e)}")

    def format_order_items(self, order):
        """Helper to format order items for display"""
        items_text = ""
        for item in order.items.all():
            items_text += f"     • {item.quantity}x {item.product_name} - ${item.total_price}\n"
        return items_text.rstrip()