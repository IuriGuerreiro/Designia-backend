from django.urls import path
from . import views
from . import PayoutViews
from . import AdminPayoutViews

app_name = 'payment_system'

urlpatterns = [
    # Stripe Checkout endpoints
    path('checkout_session/', views.create_checkout_session, name='create_checkout_session'),
    path('checkout_session/retry/<uuid:order_id>/', views.create_checkout_failed_checkout, name='create_retry_checkout_session'),

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
    path('stripe/holds/', PayoutViews.get_seller_payment_holds, name='get_seller_payment_holds'),

    # Transfer endpoints
    path('transfer/', views.transfer_payment_to_seller, name='transfer_payment_to_seller'),

    # Payout endpoints
    path('payout/', PayoutViews.seller_payout, name='seller_payout'),
    path('payouts/', PayoutViews.user_payouts_list, name='user_payouts_list'),
    path('payouts/<uuid:payout_id>/', PayoutViews.payout_detail, name='payout_detail'),
    path('payouts/<uuid:payout_id>/orders/', PayoutViews.payout_orders, name='payout_orders'),

    # Admin endpoints
    path('admin/payouts/', AdminPayoutViews.admin_list_all_payouts, name='admin_list_all_payouts'),
    path('admin/transactions/', AdminPayoutViews.admin_list_all_transactions, name='admin_list_all_transactions'),
]