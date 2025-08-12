from django.urls import path
from . import views

app_name = 'payment_system'

urlpatterns = [
    # Stripe Checkout endpoints
    path('checkout_session/', views.create_checkout_session, name='create_checkout_session'),
    path('session_status/', views.checkout_session_status, name='checkout_session_status'),
    
    # Order Management
    path('orders/<uuid:order_id>/cancel/', views.cancel_order, name='cancel_order'),
    
    # Payment Tracker endpoints
    path('trackers/', views.payment_tracker_list, name='payment_tracker_list'),
    path('trackers/<uuid:tracker_id>/', views.payment_tracker_detail, name='payment_tracker_detail'),
    path('trackers/create/', views.create_payment_tracker, name='create_payment_tracker'),
    
    # Webhook endpoints
    path('stripe_webhook/', views.stripe_webhook, name='stripe_webhook'),
    path('webhook_events/', views.webhook_events_list, name='webhook_events_list'),
    
    # User summary
    path('summary/', views.user_payment_summary, name='user_payment_summary'),
    
    # Health check
    path('health/', views.health_check, name='health_check'),
]