from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import PaymentTracker, WebhookEvent


@admin.register(PaymentTracker)
class PaymentTrackerAdmin(admin.ModelAdmin):
    """Simple admin interface for payment tracking"""
    
    list_display = [
        'id_short', 'stripe_payment_intent_short', 'stripe_refund_short',
        'order_link', 'user_link', 'transaction_type', 'status_badge',
        'amount_display', 'created_at'
    ]
    
    list_filter = [
        'transaction_type', 'status', 'currency', 'created_at'
    ]
    
    search_fields = [
        'stripe_payment_intent_id', 'stripe_refund_id', 'order__id',
        'user__username', 'user__email', 'notes'
    ]
    
    readonly_fields = ['id', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'transaction_type', 'status', 'amount', 'currency')
        }),
        ('Stripe IDs', {
            'fields': ('stripe_payment_intent_id', 'stripe_refund_id')
        }),
        ('Relationships', {
            'fields': ('order', 'user')
        }),
        ('Additional Info', {
            'fields': ('notes',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    def id_short(self, obj):
        return str(obj.id)[:8] + '...'
    id_short.short_description = 'ID'
    
    def stripe_payment_intent_short(self, obj):
        if obj.stripe_payment_intent_id:
            return obj.stripe_payment_intent_id[:15] + '...'
        return '-'
    stripe_payment_intent_short.short_description = 'Payment Intent'
    
    def stripe_refund_short(self, obj):
        if obj.stripe_refund_id:
            return obj.stripe_refund_id[:15] + '...'
        return '-'
    stripe_refund_short.short_description = 'Refund ID'
    
    def order_link(self, obj):
        if obj.order:
            url = reverse('admin:marketplace_order_change', args=[obj.order.id])
            return format_html('<a href="{}">{}</a>', url, str(obj.order.id)[:8])
        return '-'
    order_link.short_description = 'Order'
    
    def user_link(self, obj):
        if obj.user:
            url = reverse('admin:authentication_customuser_change', args=[obj.user.id])
            return format_html('<a href="{}">{}</a>', url, obj.user.username)
        return '-'
    user_link.short_description = 'User'
    
    def status_badge(self, obj):
        colors = {
            'succeeded': 'green',
            'failed': 'red',
            'pending': 'orange',
            'refunded': 'blue',
            'canceled': 'gray',
        }
        color = colors.get(obj.status, 'black')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def amount_display(self, obj):
        return f"${obj.amount:.2f} {obj.currency}"
    amount_display.short_description = 'Amount'


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    """Simple admin interface for webhook events"""
    
    list_display = [
        'stripe_event_id_short', 'event_type', 'status',
        'processing_attempts', 'payment_tracker_link', 'created_at'
    ]
    
    list_filter = ['status', 'event_type', 'created_at']
    
    search_fields = ['stripe_event_id', 'event_type']
    
    readonly_fields = ['stripe_event_id', 'event_data', 'created_at', 'processed_at']
    
    fieldsets = (
        ('Event Details', {
            'fields': ('stripe_event_id', 'event_type', 'status')
        }),
        ('Processing', {
            'fields': ('processing_attempts', 'last_processing_error')
        }),
        ('Relations', {
            'fields': ('payment_tracker',)
        }),
        ('Data', {
            'fields': ('event_data',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'processed_at')
        }),
    )
    
    def stripe_event_id_short(self, obj):
        return obj.stripe_event_id[:20] + '...' if len(obj.stripe_event_id) > 20 else obj.stripe_event_id
    stripe_event_id_short.short_description = 'Event ID'
    
    def payment_tracker_link(self, obj):
        if obj.payment_tracker:
            url = reverse('admin:payment_system_paymenttracker_change', args=[obj.payment_tracker.id])
            return format_html('<a href="{}">{}</a>', url, str(obj.payment_tracker.id)[:8])
        return '-'
    payment_tracker_link.short_description = 'Payment Tracker'