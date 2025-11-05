from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import PaymentTracker, PaymentTransaction


@admin.register(PaymentTracker)
class PaymentTrackerAdmin(admin.ModelAdmin):
    """Simple admin interface for payment tracking"""

    list_display = [
        "id_short",
        "stripe_payment_intent_short",
        "stripe_refund_short",
        "order_link",
        "user_link",
        "transaction_type",
        "status_badge",
        "amount_display",
        "created_at",
    ]

    list_filter = ["transaction_type", "status", "currency", "created_at"]

    search_fields = [
        "stripe_payment_intent_id",
        "stripe_refund_id",
        "order__id",
        "user__username",
        "user__email",
        "notes",
    ]

    readonly_fields = ["id", "created_at", "updated_at"]

    fieldsets = (
        ("Basic Information", {"fields": ("id", "transaction_type", "status", "amount", "currency")}),
        ("Stripe IDs", {"fields": ("stripe_payment_intent_id", "stripe_refund_id")}),
        ("Relationships", {"fields": ("order", "user")}),
        ("Additional Info", {"fields": ("notes",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    def id_short(self, obj):
        return str(obj.id)[:8] + "..."

    id_short.short_description = "ID"

    def stripe_payment_intent_short(self, obj):
        if obj.stripe_payment_intent_id:
            return obj.stripe_payment_intent_id[:15] + "..."
        return "-"

    stripe_payment_intent_short.short_description = "Payment Intent"

    def stripe_refund_short(self, obj):
        if obj.stripe_refund_id:
            return obj.stripe_refund_id[:15] + "..."
        return "-"

    stripe_refund_short.short_description = "Refund ID"

    def order_link(self, obj):
        if obj.order:
            url = reverse("admin:marketplace_order_change", args=[obj.order.id])
            return format_html('<a href="{}">{}</a>', url, str(obj.order.id)[:8])
        return "-"

    order_link.short_description = "Order"

    def user_link(self, obj):
        if obj.user:
            url = reverse("admin:authentication_customuser_change", args=[obj.user.id])
            return format_html('<a href="{}">{}</a>', url, obj.user.username)
        return "-"

    user_link.short_description = "User"

    def status_badge(self, obj):
        colors = {
            "succeeded": "green",
            "failed": "red",
            "pending": "orange",
            "refunded": "blue",
            "canceled": "gray",
        }
        color = colors.get(obj.status, "black")
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_status_display())

    status_badge.short_description = "Status"

    def amount_display(self, obj):
        return f"${obj.amount:.2f} {obj.currency}"

    amount_display.short_description = "Amount"


# PaymentItem inline removed - items are now tracked in item_names field


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    """Comprehensive admin interface for payment transactions"""

    list_display = [
        "id_short",
        "seller_link",
        "buyer_link",
        "status_badge",
        "gross_amount_display",
        "net_amount_display",
        "hold_status",
        "purchase_date",
        "days_remaining_display",
    ]

    list_filter = ["status", "hold_reason", "currency", "purchase_date", "payment_received_date"]

    search_fields = [
        "stripe_payment_intent_id",
        "stripe_checkout_session_id",
        "seller__username",
        "seller__email",
        "buyer__username",
        "buyer__email",
        "item_names",
        "notes",
        "hold_notes",
    ]

    readonly_fields = [
        "id",
        "stripe_payment_intent_id",
        "stripe_checkout_session_id",
        "net_amount",
        "purchase_date",
        "payment_received_date",
        "planned_release_date",
        "created_at",
        "updated_at",
    ]

    fieldsets = (
        (
            "Transaction Details",
            {"fields": ("id", "status", "gross_amount", "platform_fee", "stripe_fee", "net_amount", "currency")},
        ),
        ("Parties", {"fields": ("seller", "buyer", "order")}),
        ("Items", {"fields": ("item_count", "item_names")}),
        ("Stripe Information", {"fields": ("stripe_payment_intent_id", "stripe_checkout_session_id")}),
        (
            "Hold System",
            {
                "fields": (
                    "hold_reason",
                    "days_to_hold",
                    "hold_start_date",
                    "planned_release_date",
                    "actual_release_date",
                    "released_by",
                    "hold_notes",
                )
            },
        ),
        ("Dates", {"fields": ("purchase_date", "payment_received_date")}),
        ("Additional Info", {"fields": ("notes", "metadata")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    actions = ["release_selected_payments"]

    def id_short(self, obj):
        return str(obj.id)[:8] + "..."

    id_short.short_description = "ID"

    def seller_link(self, obj):
        url = reverse("admin:authentication_customuser_change", args=[obj.seller.id])
        return format_html('<a href="{}">{}</a>', url, obj.seller.username)

    seller_link.short_description = "Seller"

    def buyer_link(self, obj):
        url = reverse("admin:authentication_customuser_change", args=[obj.buyer.id])
        return format_html('<a href="{}">{}</a>', url, obj.buyer.username)

    buyer_link.short_description = "Buyer"

    def status_badge(self, obj):
        colors = {
            "pending": "orange",
            "held": "blue",
            "processing": "yellow",
            "released": "green",
            "disputed": "red",
            "refunded": "gray",
            "failed": "red",
        }
        color = colors.get(obj.status, "black")
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_status_display())

    status_badge.short_description = "Status"

    def gross_amount_display(self, obj):
        return f"${obj.gross_amount:.2f}"

    gross_amount_display.short_description = "Gross Amount"

    def net_amount_display(self, obj):
        return f"${obj.net_amount:.2f}"

    net_amount_display.short_description = "Net Amount"

    def hold_status(self, obj):
        if obj.status == "held":
            if obj.can_be_released:
                return format_html('<span style="color: red;">Ready for release</span>')
            else:
                days_left = obj.days_remaining
                return format_html('<span style="color: orange;">Held ({} days remaining)</span>', days_left)
        elif obj.status == "released":
            return format_html('<span style="color: green;">Released</span>')
        else:
            return format_html('<span style="color: gray;">{}</span>', obj.get_status_display())

    hold_status.short_description = "Hold Status"

    def days_remaining_display(self, obj):
        if obj.status == "held":
            days = obj.days_remaining
            if days > 0:
                return f"{days} days"
            else:
                return "Ready to release"
        elif obj.status == "released" and obj.actual_release_date:
            return "Released"
        return "-"

    days_remaining_display.short_description = "Days Remaining"

    def release_selected_payments(self, request, queryset):
        """Admin action to release selected payments"""
        released_count = 0
        for payment in queryset.filter(status="held"):
            success = payment.release_payment(
                released_by=request.user, notes=f"Manually released by admin {request.user.username}"
            )
            if success:
                released_count += 1

        self.message_user(request, f"Manually released {released_count} payments.")

    release_selected_payments.short_description = "Manually release selected held payments"
