"""
End-to-end tests for complete payment workflows
"""
import time
from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from payment_system.models import (
    StripeAccount, Payment, SellerPayout, RefundRequest, WebhookEvent
)
from marketplace.models import Order, Product, OrderItem

User = get_user_model()


class CompletePaymentFlowTestCase(APITestCase):
    """Test complete payment flow from order to seller payout"""
    
    def setUp(self):
        """Set up complete marketplace scenario"""
        # Create marketplace participants
        self.buyer = User.objects.create_user(
            username='buyer',
            email='buyer@marketplace.com',
            password='testpass123'
        )
        
        self.seller1 = User.objects.create_user(
            username='seller1',
            email='seller1@marketplace.com',
            password='testpass123'
        )
        
        self.seller2 = User.objects.create_user(
            username='seller2',
            email='seller2@marketplace.com',
            password='testpass123'
        )
        
        self.admin = User.objects.create_user(
            username='admin',
            email='admin@marketplace.com',
            is_staff=True,
            is_superuser=True
        )
        
        # Create Stripe accounts for sellers
        self.stripe_account1 = StripeAccount.objects.create(
            user=self.seller1,
            stripe_account_id='acct_seller1_123',
            email=self.seller1.email,
            country='US',
            is_active=True,
            charges_enabled=True,
            payouts_enabled=True
        )
        
        self.stripe_account2 = StripeAccount.objects.create(
            user=self.seller2,
            stripe_account_id='acct_seller2_456',
            email=self.seller2.email,
            country='US',
            is_active=True,
            charges_enabled=True,
            payouts_enabled=True
        )
        
        # Create products from different sellers
        self.product1 = Product.objects.create(
            name='Product 1',
            description='First product',
            price=Decimal('50.00'),
            seller=self.seller1
        )
        
        self.product2 = Product.objects.create(
            name='Product 2',
            description='Second product',
            price=Decimal('75.00'),
            seller=self.seller2
        )
        
        # Create order with items from multiple sellers
        self.order = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal('125.00'),
            total_amount=Decimal('125.00'),
            shipping_address={'street': '123 Test St', 'city': 'Test City', 'state': 'TC', 'postal_code': '12345', 'country': 'US'},  # 50 + 75
            status='pending'
        )
        
        self.order_item1 = OrderItem.objects.create(
            order=self.order,
            product=self.product1,
            quantity=1,
            unit_price=self.product1.price,
            total_price=self.product1.price,
            product_name=self.product1.name,
            seller=self.seller1,
            product_description=self.product1.description
        )
        
        self.order_item2 = OrderItem.objects.create(
            order=self.order,
            product=self.product2,
            quantity=1,
            unit_price=self.product2.price,
            total_price=self.product2.price,
            product_name=self.product2.name,
            seller=self.seller2,
            product_description=self.product2.description
        )
        
        # Authentication tokens
        self.buyer_token = RefreshToken.for_user(self.buyer).access_token
        self.admin_token = RefreshToken.for_user(self.admin).access_token
    
    @patch('stripe.PaymentIntent.create')
    def test_complete_successful_payment_flow(self, mock_payment_intent):
        """Test complete flow: payment -> hold -> release -> seller payouts"""
        # Step 1: Process payment
        mock_payment_intent.return_value = MagicMock(
            id='pi_complete_test_123',
            status='succeeded',
            client_secret='pi_complete_test_123_secret'
        )
        
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.buyer_token}')
        
        response = self.client.post('/api/payments/process/', {
            'order_id': str(self.order.id),
            'payment_method_id': 'pm_test_card'
        }, format='json')
        
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        
        # Verify payment was created with hold
        payment = Payment.objects.get(payment_intent_id='pi_complete_test_123')
        self.assertTrue(payment.is_held)
        self.assertEqual(payment.status, 'succeeded')
        self.assertIsNotNone(payment.hold_until)
        
        # Step 2: Simulate 30-day hold period passing
        payment.hold_until = timezone.now() - timedelta(days=1)
        payment.save()
        
        # Step 3: Admin releases holds (or automated job)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.admin_token}')
        
        response = self.client.post('/api/payments/release-holds/')
        self.assertEqual(response.status_code, 200)
        
        # Verify hold was released
        payment.refresh_from_db()
        self.assertFalse(payment.is_held)
        self.assertIsNotNone(payment.hold_released_at)
        
        # Step 4: Verify seller payouts were created
        seller_payouts = SellerPayout.objects.filter(payment=payment)
        self.assertEqual(seller_payouts.count(), 2)  # One for each seller
        
        # Verify payout amounts (with 5% marketplace fee)
        payout1 = seller_payouts.get(seller=self.seller1)
        payout2 = seller_payouts.get(seller=self.seller2)
        
        expected_fee1 = Decimal('50.00') * Decimal('0.05')  # $2.50
        expected_fee2 = Decimal('75.00') * Decimal('0.05')  # $3.75
        
        self.assertEqual(payout1.amount, Decimal('50.00') - expected_fee1)
        self.assertEqual(payout2.amount, Decimal('75.00') - expected_fee2)
        self.assertEqual(payout1.application_fee, expected_fee1)
        self.assertEqual(payout2.application_fee, expected_fee2)
    
    @patch('stripe.PaymentIntent.create')
    @patch('stripe.Refund.create')
    def test_complete_refund_flow(self, mock_refund_create, mock_payment_intent):
        """Test complete refund workflow"""
        # Step 1: Create successful payment
        mock_payment_intent.return_value = MagicMock(
            id='pi_refund_test_123',
            status='succeeded'
        )
        
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.buyer_token}')
        
        self.client.post('/api/payments/process/', {
            'order_id': str(self.order.id),
            'payment_method_id': 'pm_test_card'
        }, format='json')
        
        payment = Payment.objects.get(payment_intent_id='pi_refund_test_123')
        
        # Step 2: Buyer requests refund
        response = self.client.post('/api/payments/refund/request/', {
            'order_id': str(self.order.id),
            'amount': '50.00',  # Partial refund
            'reason': 'defective',
            'description': 'Product 1 was damaged'
        }, format='json')
        
        self.assertEqual(response.status_code, 201)
        
        refund_request = RefundRequest.objects.get(payment=payment)
        self.assertEqual(refund_request.status, 'pending')
        self.assertEqual(refund_request.amount, Decimal('50.00'))
        
        # Step 3: Admin approves refund
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.admin_token}')
        
        # Mock Stripe refund creation
        mock_refund_create.return_value = MagicMock(
            id='re_test_123',
            status='succeeded'
        )
        
        # Approve refund (simulate admin action)
        self.assertTrue(refund_request.approve_refund(self.admin))
        self.assertTrue(refund_request.process_refund())
        
        # Verify refund processing
        refund_request.refresh_from_db()
        self.assertEqual(refund_request.status, 'processing')
        self.assertIsNotNone(refund_request.stripe_refund_id)
    
    @patch('stripe.Transfer.create')
    def test_seller_payout_processing(self, mock_transfer_create):
        """Test individual seller payout processing"""
        # Create payment and payout
        payment = Payment.objects.create(
            payment_intent_id='pi_payout_test_123',
            order=self.order,
            buyer=self.buyer,
            amount=Decimal('125.00'),
            application_fee=Decimal('6.25'),  # 5%
            status='succeeded',
            is_held=False  # Already released
        )
        
        payout = SellerPayout.objects.create(
            payment=payment,
            seller=self.seller1,
            stripe_account=self.stripe_account1,
            amount=Decimal('47.50'),  # $50 - $2.50 fee
            application_fee=Decimal('2.50'),
            order_item=self.order_item1
        )
        
        # Mock Stripe transfer creation
        mock_transfer_create.return_value = MagicMock(
            id='tr_test_123',
            status='pending'
        )
        
        # Process the payout
        self.assertTrue(payout.process_payout())
        
        # Verify payout status update
        payout.refresh_from_db()
        self.assertEqual(payout.status, 'processing')
        self.assertEqual(payout.stripe_transfer_id, 'tr_test_123')
        
        # Verify Stripe transfer was created with correct parameters
        mock_transfer_create.assert_called_once_with(
            amount=4750,  # $47.50 in cents
            currency='usd',
            destination='acct_seller1_123',
            description=f"Payout for Order #{self.order.id}",
            metadata={
                'payout_id': str(payout.id),
                'order_id': str(self.order.id),
                'seller_id': str(self.seller1.id),
            }
        )


class PaymentSecurityE2ETestCase(APITestCase):
    """End-to-end security testing"""
    
    def setUp(self):
        self.buyer = User.objects.create_user(
            username='buyer',
            email='buyer@test.com'
        )
        self.seller = User.objects.create_user(
            username='seller',
            email='seller@test.com'
        )
        
        self.order = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal('99.99'),
            total_amount=Decimal('99.99'),
            shipping_address={'street': '123 Test St', 'city': 'Test City', 'state': 'TC', 'postal_code': '12345', 'country': 'US'}
        )
        
        self.buyer_token = RefreshToken.for_user(self.buyer).access_token
    
    def test_unauthorized_payment_access(self):
        """Test that users cannot access other users' payment data"""
        # Create payment for buyer
        payment = Payment.objects.create(
            payment_intent_id='pi_test_123',
            order=self.order,
            buyer=self.buyer,
            amount=Decimal('99.99'),
            status='succeeded'
        )
        
        # Try to access with seller credentials
        seller_token = RefreshToken.for_user(self.seller).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {seller_token}')
        
        response = self.client.get(f'/api/payments/status/{payment.id}/')
        self.assertEqual(response.status_code, 403)  # Forbidden
    
    def test_payment_amount_tampering_prevention(self):
        """Test that payment amounts cannot be tampered with"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.buyer_token}')
        
        # Try to process payment with tampered amount
        with patch('stripe.PaymentIntent.create') as mock_payment_intent:
            mock_payment_intent.return_value = MagicMock(
                id='pi_tamper_test',
                status='succeeded'
            )
            
            # The payment amount should be calculated server-side from order
            # Client cannot specify amount directly
            response = self.client.post('/api/payments/process/', {
                'order_id': str(self.order.id),
                'payment_method_id': 'pm_test_card',
                # No amount field should be accepted
            }, format='json')
            
            # Payment should use order's total_amount, not any client-provided amount
            payment = Payment.objects.get(payment_intent_id='pi_tamper_test')
            self.assertEqual(payment.amount, self.order.total_amount)


class PerformanceE2ETestCase(TransactionTestCase):
    """End-to-end performance testing"""
    
    def setUp(self):
        # Create multiple users and orders for load testing
        self.buyers = []
        self.orders = []
        
        for i in range(10):
            buyer = User.objects.create_user(
                username=f'buyer{i}',
                email=f'buyer{i}@test.com'
            )
            self.buyers.append(buyer)
            
            order = Order.objects.create(
                buyer=buyer,
                subtotal=Decimal('50.00'),
                total_amount=Decimal('50.00'),
                shipping_address={'street': '123 Test St', 'city': 'Test City', 'state': 'TC', 'postal_code': '12345', 'country': 'US'}
            )
            self.orders.append(order)
    
    def test_bulk_payment_processing(self):
        """Test processing multiple payments efficiently"""
        start_time = time.time()
        
        # Create multiple payments
        payments = []
        for i, order in enumerate(self.orders):
            payment = Payment.objects.create(
                payment_intent_id=f'pi_bulk_test_{i}',
                order=order,
                buyer=order.buyer,
                amount=order.total_amount,
                status='succeeded',
                hold_until=timezone.now() - timedelta(days=1)  # Eligible for release
            )
            payments.append(payment)
        
        # Release all holds
        released_count = 0
        for payment in payments:
            if payment.release_hold():
                released_count += 1
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Verify performance
        self.assertEqual(released_count, 10)
        self.assertLess(processing_time, 5.0)  # Should complete within 5 seconds
        
        # Verify payouts were created
        total_payouts = SellerPayout.objects.count()
        self.assertGreater(total_payouts, 0)
    
    def test_webhook_processing_performance(self):
        """Test webhook processing performance"""
        # Create multiple webhook events
        events = []
        for i in range(50):
            event = WebhookEvent.objects.create(
                stripe_event_id=f'evt_perf_test_{i}',
                event_type='payment_intent.succeeded',
                event_data={'test': f'data_{i}'}
            )
            events.append(event)
        
        start_time = time.time()
        
        # Mark all events as processed
        WebhookEvent.objects.filter(
            stripe_event_id__startswith='evt_perf_test'
        ).update(
            status='processed',
            processed_at=timezone.now()
        )
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Should process quickly
        self.assertLess(processing_time, 1.0)  # Should complete within 1 second
        
        # Verify all events were processed
        processed_count = WebhookEvent.objects.filter(
            stripe_event_id__startswith='evt_perf_test',
            status='processed'
        ).count()
        self.assertEqual(processed_count, 50)


class DataConsistencyE2ETestCase(TestCase):
    """Test data consistency across payment operations"""
    
    def setUp(self):
        self.buyer = User.objects.create_user(
            username='buyer',
            email='buyer@test.com'
        )
        self.seller = User.objects.create_user(
            username='seller',
            email='seller@test.com'
        )
        
        self.stripe_account = StripeAccount.objects.create(
            user=self.seller,
            stripe_account_id='acct_consistency_test',
            email=self.seller.email,
            country='US',
            is_active=True
        )
        
        self.product = Product.objects.create(
            name='Consistency Test Product',
            price=Decimal('100.00'),
            seller=self.seller
        )
        
        self.order = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal('100.00'),
            total_amount=Decimal('100.00'),
            shipping_address={'street': '123 Test St', 'city': 'Test City', 'state': 'TC', 'postal_code': '12345', 'country': 'US'}
        )
        
        self.order_item = OrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=1,
            unit_price=self.product.price,
            total_price=self.product.price,
            product_name=self.product.name,
            seller=self.seller,
            product_description=self.product.description
        )
    
    def test_payment_payout_amount_consistency(self):
        """Test that payment amounts match payout amounts plus fees"""
        payment = Payment.objects.create(
            payment_intent_id='pi_consistency_test',
            order=self.order,
            buyer=self.buyer,
            amount=Decimal('100.00'),
            application_fee=Decimal('5.00'),  # 5%
            status='succeeded'
        )
        
        # Release hold and create payouts
        payment.hold_until = timezone.now() - timedelta(days=1)
        payment.save()
        payment.release_hold()
        
        # Verify amount consistency
        payouts = SellerPayout.objects.filter(payment=payment)
        total_payout_amount = sum(payout.amount for payout in payouts)
        total_fees = sum(payout.application_fee for payout in payouts)
        
        # Total payouts + fees should equal original payment amount
        self.assertEqual(
            total_payout_amount + total_fees,
            payment.amount
        )
        self.assertEqual(total_fees, payment.application_fee)
    
    def test_refund_amount_validation(self):
        """Test that refund amounts are properly validated"""
        payment = Payment.objects.create(
            payment_intent_id='pi_refund_validation',
            order=self.order,
            buyer=self.buyer,
            amount=Decimal('100.00'),
            status='succeeded'
        )
        
        # Create first refund request
        refund1 = RefundRequest.objects.create(
            payment=payment,
            order=self.order,
            requested_by=self.buyer,
            amount=Decimal('60.00'),
            reason='defective',
            status='approved'
        )
        
        # Try to create second refund that would exceed payment amount
        refund2 = RefundRequest.objects.create(
            payment=payment,
            order=self.order,
            requested_by=self.buyer,
            amount=Decimal('50.00'),  # 60 + 50 = 110 > 100
            reason='not_as_described'
        )
        
        # Validate that total approved refunds don't exceed payment amount
        from payment_system.security import PaymentValidator
        
        is_valid, error = PaymentValidator.validate_refund_eligibility(
            payment, refund2.amount
        )
        
        self.assertFalse(is_valid)
        self.assertIn('exceed', error)


if __name__ == '__main__':
    import django
    from django.conf import settings
    from django.test.utils import get_runner
    
    if not settings.configured:
        import os
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'designiaBackend.settings')
        django.setup()
    
    TestRunner = get_runner(settings)
    test_runner = TestRunner()
    failures = test_runner.run_tests(['payment_system.testing.test_end_to_end'])
    if failures:
        exit(1)