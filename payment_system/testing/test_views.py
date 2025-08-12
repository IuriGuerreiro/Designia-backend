"""
Integration tests for payment system views and API endpoints
"""
import json
from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from payment_system.models import (
    StripeAccount, Payment, SellerPayout, RefundRequest, WebhookEvent
)
from marketplace.models import Order, Product, OrderItem

User = get_user_model()


class PaymentAPITestCase(APITestCase):
    def setUp(self):
        """Set up test data and authentication"""
        # Create test users
        self.buyer = User.objects.create_user(
            username='testbuyer',
            email='buyer@test.com',
            password='testpass123'
        )
        self.seller = User.objects.create_user(
            username='testseller',
            email='seller@test.com',
            password='testpass123'
        )
        self.admin = User.objects.create_user(
            username='admin',
            email='admin@test.com',
            is_staff=True,
            is_superuser=True
        )
        
        # Create JWT tokens for authentication
        self.buyer_token = RefreshToken.for_user(self.buyer).access_token
        self.seller_token = RefreshToken.for_user(self.seller).access_token
        self.admin_token = RefreshToken.for_user(self.admin).access_token
        
        # Create test data
        self.stripe_account = StripeAccount.objects.create(
            user=self.seller,
            stripe_account_id='acct_test123',
            email=self.seller.email,
            country='US',
            is_active=True,
            charges_enabled=True,
            payouts_enabled=True
        )
        
        self.product = Product.objects.create(
            name='Test Product',
            description='A test product',
            price=Decimal('99.99'),
            seller=self.seller
        )
        
        self.order = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal('99.99'),
            total_amount=Decimal('99.99'),
            shipping_address={'street': '123 Test St', 'city': 'Test City', 'state': 'TC', 'postal_code': '12345', 'country': 'US'},
            status='pending'
        )
        
        self.order_item = OrderItem.objects.create(
            order=self.order,
            product=self.product,
            seller=self.seller,
            quantity=1,
            unit_price=self.product.price,
            total_price=self.product.price,
            product_name=self.product.name,
            product_description=self.product.description
)
    
    def authenticate_buyer(self):
        """Authenticate as buyer"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.buyer_token}')
    
    def authenticate_seller(self):
        """Authenticate as seller"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.seller_token}')
    
    def authenticate_admin(self):
        """Authenticate as admin"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.admin_token}')


class PaymentProcessingViewTestCase(PaymentAPITestCase):
    """Test payment processing API endpoint"""
    
    @patch('stripe.PaymentIntent.create')
    def test_successful_payment_processing(self, mock_payment_intent):
        """Test successful payment processing"""
        # Mock Stripe PaymentIntent response
        mock_payment_intent.return_value = MagicMock(
            id='pi_test123',
            status='succeeded',
            client_secret='pi_test123_secret'
        )
        
        self.authenticate_buyer()
        
        response = self.client.post('/api/payments/process/', {
            'order_id': str(self.order.id),
            'payment_method_id': 'pm_test123'
        }, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('payment_id', data)
        
        # Verify payment was created
        payment = Payment.objects.get(payment_intent_id='pi_test123')
        self.assertEqual(payment.order, self.order)
        self.assertEqual(payment.buyer, self.buyer)
        self.assertEqual(payment.status, 'succeeded')
    
    @patch('stripe.PaymentIntent.create')
    def test_payment_requiring_action(self, mock_payment_intent):
        """Test payment that requires 3D Secure authentication"""
        # Mock Stripe PaymentIntent requiring action
        mock_payment_intent.return_value = MagicMock(
            id='pi_test123',
            status='requires_action',
            client_secret='pi_test123_secret',
            next_action=MagicMock(type='use_stripe_sdk')
        )
        
        self.authenticate_buyer()
        
        response = self.client.post('/api/payments/process/', {
            'order_id': str(self.order.id),
            'payment_method_id': 'pm_test123'
        }, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(data['requires_action'])
        self.assertIn('payment_intent', data)
    
    def test_payment_processing_unauthorized(self):
        """Test payment processing without authentication"""
        response = self.client.post('/api/payments/process/', {
            'order_id': str(self.order.id),
            'payment_method_id': 'pm_test123'
        }, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_payment_processing_invalid_order(self):
        """Test payment processing with invalid order ID"""
        self.authenticate_buyer()
        
        response = self.client.post('/api/payments/process/', {
            'order_id': '00000000-0000-0000-0000-000000000000',
            'payment_method_id': 'pm_test123'
        }, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_duplicate_payment_processing(self):
        """Test processing payment for already paid order"""
        # Create existing successful payment
        Payment.objects.create(
            payment_intent_id='pi_existing',
            order=self.order,
            buyer=self.buyer,
            amount=self.order.total_amount,
            status='succeeded'
        )
        
        self.authenticate_buyer()
        
        response = self.client.post('/api/payments/process/', {
            'order_id': str(self.order.id),
            'payment_method_id': 'pm_test123'
        }, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('already paid', data['error'])


class StripeAccountViewTestCase(PaymentAPITestCase):
    """Test Stripe account management endpoints"""
    
    @patch('stripe.Account.create')
    @patch('stripe.AccountLink.create')
    def test_create_stripe_account(self, mock_account_link, mock_account):
        """Test creating a new Stripe Connect account"""
        # Mock Stripe responses
        mock_account.return_value = MagicMock(id='acct_new123')
        mock_account_link.return_value = MagicMock(
            url='https://connect.stripe.com/setup/acct_new123'
        )
        
        # Create user without existing Stripe account
        new_seller = User.objects.create_user(
            username='newseller',
            email='newseller@test.com'
        )
        new_seller_token = RefreshToken.for_user(new_seller).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {new_seller_token}')
        
        response = self.client.post('/api/payments/stripe-account/create/', {
            'country': 'US'
        }, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data['account_id'], 'acct_new123')
        self.assertIn('onboarding_url', data)
        
        # Verify StripeAccount was created
        stripe_account = StripeAccount.objects.get(user=new_seller)
        self.assertEqual(stripe_account.stripe_account_id, 'acct_new123')
    
    def test_create_duplicate_stripe_account(self):
        """Test creating Stripe account for user who already has one"""
        self.authenticate_seller()  # This user already has a Stripe account
        
        response = self.client.post('/api/payments/stripe-account/create/', {
            'country': 'US'
        }, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = response.json()
        self.assertIn('error', data)
    
    @patch('stripe.Account.retrieve')
    def test_get_stripe_account_status(self, mock_account_retrieve):
        """Test retrieving Stripe account status"""
        # Mock Stripe account response
        mock_account_retrieve.return_value = MagicMock(
            charges_enabled=True,
            payouts_enabled=True,
            details_submitted=True
        )
        
        self.authenticate_seller()
        
        response = self.client.get('/api/payments/stripe-account/status/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(data['charges_enabled'])
        self.assertTrue(data['payouts_enabled'])
        self.assertTrue(data['details_submitted'])
    
    def test_get_stripe_account_status_not_found(self):
        """Test retrieving status for non-existent Stripe account"""
        # Create user without Stripe account
        new_user = User.objects.create_user(
            username='newuser',
            email='newuser@test.com'
        )
        new_user_token = RefreshToken.for_user(new_user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {new_user_token}')
        
        response = self.client.get('/api/payments/stripe-account/status/')
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class PaymentStatusViewTestCase(PaymentAPITestCase):
    """Test payment status retrieval endpoints"""
    
    def test_get_payment_status_as_buyer(self):
        """Test getting payment status as the buyer"""
        payment = Payment.objects.create(
            payment_intent_id='pi_test123',
            order=self.order,
            buyer=self.buyer,
            amount=Decimal('99.99'),
            status='succeeded'
        )
        
        self.authenticate_buyer()
        
        response = self.client.get(f'/api/payments/status/{payment.id}/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data['payment_intent_id'], 'pi_test123')
        self.assertEqual(data['status'], 'succeeded')
        self.assertIn('days_until_release', data)
    
    def test_get_payment_status_unauthorized(self):
        """Test getting payment status without proper authorization"""
        # Create payment for different buyer
        other_buyer = User.objects.create_user(
            username='otherbuyer',
            email='other@test.com'
        )
        other_order = Order.objects.create(
            buyer=other_buyer,
            subtotal=Decimal('50.00'),
            total_amount=Decimal('50.00'),
            shipping_address={'street': '123 Test St', 'city': 'Test City', 'state': 'TC', 'postal_code': '12345', 'country': 'US'}
        )
        payment = Payment.objects.create(
            payment_intent_id='pi_test123',
            order=other_order,
            buyer=other_buyer,
            amount=Decimal('50.00'),
            status='succeeded'
        )
        
        self.authenticate_buyer()  # Different user
        
        response = self.client.get(f'/api/payments/status/{payment.id}/')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_get_payment_status_as_admin(self):
        """Test that admin can access any payment status"""
        payment = Payment.objects.create(
            payment_intent_id='pi_test123',
            order=self.order,
            buyer=self.buyer,
            amount=Decimal('99.99'),
            status='succeeded'
        )
        
        self.authenticate_admin()
        
        response = self.client.get(f'/api/payments/status/{payment.id}/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class RefundRequestViewTestCase(PaymentAPITestCase):
    """Test refund request endpoints"""
    
    def test_create_refund_request(self):
        """Test creating a refund request"""
        payment = Payment.objects.create(
            payment_intent_id='pi_test123',
            order=self.order,
            buyer=self.buyer,
            amount=Decimal('99.99'),
            status='succeeded'
        )
        
        self.authenticate_buyer()
        
        response = self.client.post('/api/payments/refund/request/', {
            'order_id': str(self.order.id),
            'amount': '50.00',
            'reason': 'defective',
            'description': 'Product was damaged'
        }, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()
        self.assertIn('refund_number', data)
        
        # Verify refund request was created
        refund_request = RefundRequest.objects.get(payment=payment)
        self.assertEqual(refund_request.requested_by, self.buyer)
        self.assertEqual(refund_request.amount, Decimal('50.00'))
        self.assertEqual(refund_request.reason, 'defective')
    
    def test_create_refund_request_excessive_amount(self):
        """Test creating refund request with amount exceeding payment"""
        payment = Payment.objects.create(
            payment_intent_id='pi_test123',
            order=self.order,
            buyer=self.buyer,
            amount=Decimal('99.99'),
            status='succeeded'
        )
        
        self.authenticate_buyer()
        
        response = self.client.post('/api/payments/refund/request/', {
            'order_id': str(self.order.id),
            'amount': '150.00',  # More than payment amount
            'reason': 'defective',
            'description': 'Product was damaged'
        }, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_create_refund_request_no_payment(self):
        """Test creating refund request for order without successful payment"""
        self.authenticate_buyer()
        
        response = self.client.post('/api/payments/refund/request/', {
            'order_id': str(self.order.id),
            'amount': '50.00',
            'reason': 'defective',
            'description': 'Product was damaged'
        }, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class SellerPayoutViewTestCase(PaymentAPITestCase):
    """Test seller payout endpoints"""
    
    def test_get_seller_payouts(self):
        """Test retrieving seller payout history"""
        payment = Payment.objects.create(
            payment_intent_id='pi_test123',
            order=self.order,
            buyer=self.buyer,
            amount=Decimal('99.99'),
            application_fee=Decimal('5.00'),
            status='succeeded'
        )
        
        payout = SellerPayout.objects.create(
            payment=payment,
            seller=self.seller,
            stripe_account=self.stripe_account,
            amount=Decimal('94.99'),
            application_fee=Decimal('5.00'),
            order_item=self.order_item,
            status='paid'
        )
        
        self.authenticate_seller()
        
        response = self.client.get('/api/payments/seller-payouts/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['amount'], '94.99')
        self.assertEqual(data[0]['status'], 'paid')


class AdminHoldReleaseViewTestCase(PaymentAPITestCase):
    """Test admin hold release endpoints"""
    
    def test_release_payment_holds_as_admin(self):
        """Test releasing payment holds as admin"""
        # Create payment eligible for hold release
        payment = Payment.objects.create(
            payment_intent_id='pi_test123',
            order=self.order,
            buyer=self.buyer,
            amount=Decimal('99.99'),
            application_fee=Decimal('5.00'),
            status='succeeded',
            hold_until=timezone.now() - timedelta(days=1)  # Past due
        )
        
        self.authenticate_admin()
        
        response = self.client.post('/api/payments/release-holds/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn('Released 1 payment holds', data['message'])
        
        # Verify hold was released
        payment.refresh_from_db()
        self.assertFalse(payment.is_held)
    
    def test_release_payment_holds_unauthorized(self):
        """Test that non-admin users cannot release holds"""
        self.authenticate_buyer()
        
        response = self.client.post('/api/payments/release-holds/')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class WebhookViewTestCase(PaymentAPITestCase):
    """Test Stripe webhook handling"""
    
    @patch('stripe.Webhook.construct_event')
    def test_webhook_payment_succeeded(self, mock_construct_event):
        """Test handling successful payment webhook"""
        # Create payment to be updated
        payment = Payment.objects.create(
            payment_intent_id='pi_test123',
            order=self.order,
            buyer=self.buyer,
            amount=Decimal('99.99'),
            status='processing'
        )
        
        # Mock webhook event
        mock_event = {
            'id': 'evt_test123',
            'type': 'payment_intent.succeeded',
            'data': {
                'object': {
                    'id': 'pi_test123',
                    'status': 'succeeded'
                }
            }
        }
        mock_construct_event.return_value = mock_event
        
        response = self.client.post(
            '/api/payments/webhooks/stripe/',
            data=json.dumps({'test': 'data'}),
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='test_signature'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify payment was updated
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'succeeded')
        
        # Verify webhook event was logged
        self.assertTrue(WebhookEvent.objects.filter(
            stripe_event_id='evt_test123'
        ).exists())
    
    def test_webhook_invalid_signature(self):
        """Test webhook with invalid signature"""
        response = self.client.post(
            '/api/payments/webhooks/stripe/',
            data=json.dumps({'test': 'data'}),
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='invalid_signature'
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


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
    failures = test_runner.run_tests(['payment_system.testing.test_views'])
    if failures:
        exit(1)