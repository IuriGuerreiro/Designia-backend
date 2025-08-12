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
]