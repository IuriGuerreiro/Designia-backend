from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from .models import PaymentTracker, WebhookEvent, PaymentTransaction, PaymentHold, PaymentItem


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


class PaymentItemInline(admin.TabularInline):
    """Inline for PaymentItems in PaymentTransaction"""
    model = PaymentItem
    extra = 0
    readonly_fields = ['product', 'order_item', 'quantity', 'unit_price', 'total_price', 'product_name']
    fields = ['product', 'quantity', 'unit_price', 'total_price', 'product_name']


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    """Comprehensive admin interface for payment transactions"""
    
    list_display = [
        'id_short', 'seller_link', 'buyer_link', 'status_badge', 
        'gross_amount_display', 'net_amount_display', 'hold_status',
        'purchase_date', 'days_held'
    ]
    
    list_filter = [
        'status', 'currency', 'purchase_date', 'payment_received_date'
    ]
    
    search_fields = [
        'stripe_payment_intent_id', 'stripe_checkout_session_id',
        'seller__username', 'seller__email', 'buyer__username', 'buyer__email',
        'item_names', 'notes'
    ]
    
    readonly_fields = [
        'id', 'stripe_payment_intent_id', 'stripe_checkout_session_id',
        'net_amount', 'purchase_date', 'payment_received_date',
        'created_at', 'updated_at'
    ]
    
    inlines = [PaymentItemInline]
    
    fieldsets = (
        ('Transaction Details', {
            'fields': ('id', 'status', 'gross_amount', 'platform_fee', 'stripe_fee', 'net_amount', 'currency')
        }),
        ('Parties', {
            'fields': ('seller', 'buyer', 'order')
        }),
        ('Items', {
            'fields': ('item_count', 'item_names')
        }),
        ('Stripe Information', {
            'fields': ('stripe_payment_intent_id', 'stripe_checkout_session_id')
        }),
        ('Dates', {
            'fields': ('purchase_date', 'payment_received_date', 'hold_release_date')
        }),
        ('Additional Info', {
            'fields': ('notes', 'metadata')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    actions = ['release_selected_payments']
    
    def id_short(self, obj):
        return str(obj.id)[:8] + '...'
    id_short.short_description = 'ID'
    
    def seller_link(self, obj):
        url = reverse('admin:authentication_customuser_change', args=[obj.seller.id])
        return format_html('<a href="{}">{}</a>', url, obj.seller.username)
    seller_link.short_description = 'Seller'
    
    def buyer_link(self, obj):
        url = reverse('admin:authentication_customuser_change', args=[obj.buyer.id])
        return format_html('<a href="{}">{}</a>', url, obj.buyer.username)
    buyer_link.short_description = 'Buyer'
    
    def status_badge(self, obj):
        colors = {
            'pending': 'orange',
            'held': 'blue',
            'processing': 'yellow',
            'released': 'green',
            'disputed': 'red',
            'refunded': 'gray',
            'failed': 'red',
        }
        color = colors.get(obj.status, 'black')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def gross_amount_display(self, obj):
        return f"${obj.gross_amount:.2f}"
    gross_amount_display.short_description = 'Gross Amount'
    
    def net_amount_display(self, obj):
        return f"${obj.net_amount:.2f}"
    net_amount_display.short_description = 'Net Amount'
    
    def hold_status(self, obj):
        try:
            hold = obj.payment_hold
            if hold.status == 'active':
                days_left = (hold.planned_release_date - timezone.now()).days
                if days_left > 0:
                    return format_html(
                        '<span style="color: orange;">Held ({} days) - Manual release required</span>',
                        days_left
                    )
                else:
                    return format_html(
                        '<span style="color: red;">Ready for manual release</span>'
                    )
            else:
                return format_html(
                    '<span style="color: green;">{}</span>',
                    hold.get_status_display()
                )
        except PaymentHold.DoesNotExist:
            return 'No hold'
    hold_status.short_description = 'Hold Status'
    
    def days_held(self, obj):
        if obj.payment_received_date:
            days = (timezone.now() - obj.payment_received_date).days
            return f"{days} days"
        return '-'
    days_held.short_description = 'Days Held'
    
    def release_selected_payments(self, request, queryset):
        """Admin action to release selected payments (manual process)"""
        released_count = 0
        for payment in queryset.filter(status='held'):
            try:
                hold = payment.payment_hold
                success = hold.release_hold(
                    released_by=request.user,
                    notes=f"Manually released by admin {request.user.username}"
                )
                if success:
                    released_count += 1
            except PaymentHold.DoesNotExist:
                # If no hold exists, release the payment directly
                success = payment.release_payment(
                    released_by=request.user,
                    notes=f"Manually released by admin {request.user.username}"
                )
                if success:
                    released_count += 1
        
        self.message_user(request, f"Manually released {released_count} payments.")
    release_selected_payments.short_description = "Manually release selected held payments"


@admin.register(PaymentHold)
class PaymentHoldAdmin(admin.ModelAdmin):
    """Admin interface for payment holds"""
    
    list_display = [
        'payment_transaction_short', 'seller_name', 'reason', 'status_badge',
        'hold_days', 'planned_release_date', 'days_remaining', 'created_by_name'
    ]
    
    list_filter = [
        'reason', 'status', 'hold_days', 'planned_release_date'
    ]
    
    search_fields = [
        'payment_transaction__seller__username',
        'payment_transaction__seller__email',
        'hold_notes', 'release_notes'
    ]
    
    readonly_fields = [
        'payment_transaction', 'hold_start_date', 'planned_release_date',
        'actual_release_date', 'created_at', 'updated_at'
    ]
    
    fieldsets = (
        ('Hold Details', {
            'fields': ('payment_transaction', 'reason', 'status', 'hold_days')
        }),
        ('Dates', {
            'fields': ('hold_start_date', 'planned_release_date', 'actual_release_date')
        }),
        ('Staff Tracking', {
            'fields': ('created_by', 'released_by')
        }),
        ('Notes', {
            'fields': ('hold_notes', 'release_notes')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    actions = ['release_selected_holds']
    
    def payment_transaction_short(self, obj):
        return str(obj.payment_transaction.id)[:8] + '...'
    payment_transaction_short.short_description = 'Transaction'
    
    def seller_name(self, obj):
        return obj.payment_transaction.seller.username
    seller_name.short_description = 'Seller'
    
    def status_badge(self, obj):
        colors = {
            'active': 'orange',
            'released': 'green',
            'expired': 'red',
            'cancelled': 'gray',
        }
        color = colors.get(obj.status, 'black')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def days_remaining(self, obj):
        if obj.status == 'active' and obj.planned_release_date:
            days = (obj.planned_release_date - timezone.now()).days
            if days > 0:
                return f"{days} days"
            else:
                return "Ready to release"
        return '-'
    days_remaining.short_description = 'Days Remaining'
    
    def created_by_name(self, obj):
        return obj.created_by.username if obj.created_by else 'System'
    created_by_name.short_description = 'Created By'
    
    def release_selected_holds(self, request, queryset):
        """Admin action to manually release selected holds"""
        released_count = 0
        for hold in queryset.filter(status='active'):
            success = hold.release_hold(
                released_by=request.user,
                notes=f"Manually released by admin {request.user.username}"
            )
            if success:
                released_count += 1
        
        self.message_user(request, f"Manually released {released_count} holds.")
    release_selected_holds.short_description = "Manually release selected holds"


@admin.register(PaymentItem)
class PaymentItemAdmin(admin.ModelAdmin):
    """Admin interface for payment items"""
    
    list_display = [
        'payment_transaction_short', 'product_name', 'quantity',
        'unit_price_display', 'total_price_display', 'seller_name'
    ]
    
    list_filter = ['created_at']
    
    search_fields = [
        'product_name', 'product_sku',
        'payment_transaction__seller__username',
        'product__name'
    ]
    
    readonly_fields = [
        'payment_transaction', 'product', 'order_item',
        'total_price', 'created_at'
    ]
    
    fieldsets = (
        ('Item Details', {
            'fields': ('payment_transaction', 'product', 'order_item')
        }),
        ('Pricing', {
            'fields': ('quantity', 'unit_price', 'total_price')
        }),
        ('Product Info', {
            'fields': ('product_name', 'product_sku')
        }),
        ('Timestamps', {
            'fields': ('created_at',)
        }),
    )
    
    def payment_transaction_short(self, obj):
        return str(obj.payment_transaction.id)[:8] + '...'
    payment_transaction_short.short_description = 'Transaction'
    
    def unit_price_display(self, obj):
        return f"${obj.unit_price:.2f}"
    unit_price_display.short_description = 'Unit Price'
    
    def total_price_display(self, obj):
        return f"${obj.total_price:.2f}"
    total_price_display.short_description = 'Total Price'
    
    def seller_name(self, obj):
        return obj.payment_transaction.seller.username
    seller_name.short_description = 'Seller'