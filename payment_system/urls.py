from django.urls import path
from . import views

app_name = 'payment_system'

urlpatterns = [
    # Stripe Checkout endpoints
    path('checkout_session/', views.create_checkout_session, name='create_checkout_session'),
    path('session_status/', views.checkout_session_status, name='checkout_session_status'),
    
    # Order Management
    path('orders/<uuid:order_id>/cancel/', views.cancel_order, name='cancel_order'),

    # Webhook endpoints
    path('stripe_webhook/', views.stripe_webhook, name='stripe_webhook'),
    path('stripe_webhook/connect/', views.stripe_webhook_connect, name='stripe_webhook_connect'),
    
    # Stripe Connect endpoints
    path('stripe/account/', views.stripe_account, name='stripe_account'),
    path('stripe/create-session/', views.create_stripe_account_session, name='create_stripe_account_session'),
    path('stripe/account-status/', views.get_stripe_account_status, name='get_stripe_account_status'),
    
    # Payment Holds endpoints
    path('stripe/holds/', views.get_seller_payment_holds, name='get_seller_payment_holds'),
    
    # Transfer endpoints
    path('transfer/', views.transfer_payment_to_seller, name='transfer_payment_to_seller'),
    
    # Payout endpoints
    path('payout/', views.seller_payout, name='seller_payout'),
]