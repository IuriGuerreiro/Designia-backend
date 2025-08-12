from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe

from .models import (
    Category, Product, ProductImage, ProductReview, ProductFavorite,
    Order, OrderItem, Cart, CartItem, ProductMetrics
)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ('image', 'alt_text', 'is_primary', 'order')
    readonly_fields = ('image_preview',)

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="100" height="100" />', obj.image.url)
        return "No Image"
    image_preview.short_description = "Preview"


class ProductReviewInline(admin.TabularInline):
    model = ProductReview
    extra = 0
    fields = ('reviewer', 'rating', 'title', 'is_active')
    readonly_fields = ('reviewer', 'rating', 'title', 'created_at')


class ProductMetricsInline(admin.StackedInline):
    model = ProductMetrics
    extra = 0
    readonly_fields = ('total_views', 'total_clicks', 'total_favorites', 
                      'total_cart_additions', 'total_sales', 'total_revenue',
                      'last_updated')


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent', 'is_active', 'product_count', 'created_at')
    list_filter = ('is_active', 'parent', 'created_at')
    search_fields = ('name', 'description')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('created_at', 'updated_at', 'product_count')
    
    fieldsets = (
        (None, {
            'fields': ('name', 'slug', 'description', 'parent')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def product_count(self, obj):
        return obj.products.filter(is_active=True).count()
    product_count.short_description = "Active Products"


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'seller', 'category', 'price', 'stock_quantity', 
                   'condition', 'is_active', 'is_featured', 'created_at')
    list_filter = ('is_active', 'is_featured', 'is_digital', 'condition', 
                  'category', 'seller', 'created_at')
    search_fields = ('name', 'description', 'brand', 'model', 'seller__username')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('id', 'slug', 'created_at', 'updated_at', 'view_count', 
                      'click_count', 'favorite_count', 'average_rating', 
                      'review_count', 'is_on_sale', 'discount_percentage')
    
    inlines = [ProductImageInline, ProductReviewInline, ProductMetricsInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'name', 'slug', 'description', 'short_description')
        }),
        ('Seller & Category', {
            'fields': ('seller', 'category')
        }),
        ('Pricing & Inventory', {
            'fields': ('price', 'original_price', 'stock_quantity', 'is_on_sale', 'discount_percentage')
        }),
        ('Product Details', {
            'fields': ('condition', 'brand', 'model', 'colors', 'materials', 'tags')
        }),
        ('Physical Properties', {
            'fields': ('weight', 'dimensions_length', 'dimensions_width', 'dimensions_height'),
            'classes': ('collapse',)
        }),
        ('Status & Visibility', {
            'fields': ('is_active', 'is_featured', 'is_digital')
        }),
        ('Metrics', {
            'fields': ('view_count', 'click_count', 'favorite_count', 'average_rating', 'review_count'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('seller', 'category')

    actions = ['make_featured', 'remove_featured', 'activate_products', 'deactivate_products']

    def make_featured(self, request, queryset):
        queryset.update(is_featured=True)
        self.message_user(request, f"{queryset.count()} products marked as featured.")
    make_featured.short_description = "Mark selected products as featured"

    def remove_featured(self, request, queryset):
        queryset.update(is_featured=False)
        self.message_user(request, f"{queryset.count()} products unmarked as featured.")
    remove_featured.short_description = "Remove featured status from selected products"

    def activate_products(self, request, queryset):
        queryset.update(is_active=True)
        self.message_user(request, f"{queryset.count()} products activated.")
    activate_products.short_description = "Activate selected products"

    def deactivate_products(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(request, f"{queryset.count()} products deactivated.")
    deactivate_products.short_description = "Deactivate selected products"


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ('product', 'alt_text', 'is_primary', 'order', 'image_preview')
    list_filter = ('is_primary', 'created_at')
    search_fields = ('product__name', 'alt_text')
    readonly_fields = ('image_preview',)

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="100" height="100" />', obj.image.url)
        return "No Image"
    image_preview.short_description = "Preview"


@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    list_display = ('product', 'reviewer', 'rating', 'title', 'is_verified_purchase', 
                   'is_active', 'created_at')
    list_filter = ('rating', 'is_verified_purchase', 'is_active', 'created_at')
    search_fields = ('product__name', 'reviewer__username', 'title', 'comment')
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        (None, {
            'fields': ('product', 'reviewer', 'rating', 'title', 'comment')
        }),
        ('Status', {
            'fields': ('is_verified_purchase', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    actions = ['approve_reviews', 'disapprove_reviews']

    def approve_reviews(self, request, queryset):
        queryset.update(is_active=True)
        self.message_user(request, f"{queryset.count()} reviews approved.")
    approve_reviews.short_description = "Approve selected reviews"

    def disapprove_reviews(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(request, f"{queryset.count()} reviews disapproved.")
    disapprove_reviews.short_description = "Disapprove selected reviews"


@admin.register(ProductFavorite)
class ProductFavoriteAdmin(admin.ModelAdmin):
    list_display = ('user', 'product', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__username', 'product__name')
    readonly_fields = ('created_at',)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product', 'seller', 'quantity', 'unit_price', 'total_price',
                      'product_name', 'product_description')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'buyer', 'status', 'payment_status', 'total_amount', 
                   'created_at', 'item_count')
    list_filter = ('status', 'payment_status', 'created_at', 'updated_at')
    search_fields = ('id', 'buyer__username', 'buyer__email')
    readonly_fields = ('id', 'created_at', 'updated_at', 'item_count')
    
    inlines = [OrderItemInline]
    
    fieldsets = (
        ('Order Information', {
            'fields': ('id', 'buyer', 'status', 'payment_status')
        }),
        ('Pricing', {
            'fields': ('subtotal', 'shipping_cost', 'tax_amount', 'discount_amount', 'total_amount')
        }),
        ('Shipping', {
            'fields': ('shipping_address', 'tracking_number', 'shipping_carrier', 
                      'shipped_at', 'delivered_at')
        }),
        ('Notes', {
            'fields': ('buyer_notes', 'admin_notes'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def item_count(self, obj):
        return obj.items.count()
    item_count.short_description = "Items"

    actions = ['mark_confirmed', 'mark_shipped', 'mark_delivered']

    def mark_confirmed(self, request, queryset):
        queryset.update(status='confirmed')
        self.message_user(request, f"{queryset.count()} orders marked as confirmed.")
    mark_confirmed.short_description = "Mark selected orders as confirmed"

    def mark_shipped(self, request, queryset):
        queryset.update(status='shipped')
        self.message_user(request, f"{queryset.count()} orders marked as shipped.")
    mark_shipped.short_description = "Mark selected orders as shipped"

    def mark_delivered(self, request, queryset):
        queryset.update(status='delivered')
        self.message_user(request, f"{queryset.count()} orders marked as delivered.")
    mark_delivered.short_description = "Mark selected orders as delivered"


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'product', 'seller', 'quantity', 'unit_price', 'total_price')
    list_filter = ('order__status', 'seller', 'order__created_at')
    search_fields = ('order__id', 'product__name', 'seller__username', 'product_name')
    readonly_fields = ('total_price',)


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ('total_price',)


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ('user', 'total_items', 'total_amount', 'created_at', 'updated_at')
    list_filter = ('created_at', 'updated_at')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('total_items', 'total_amount', 'created_at', 'updated_at')
    
    inlines = [CartItemInline]


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ('cart_user', 'product', 'quantity', 'total_price', 'added_at')
    list_filter = ('added_at',)
    search_fields = ('cart__user__username', 'product__name')
    readonly_fields = ('total_price',)

    def cart_user(self, obj):
        return obj.cart.user.username
    cart_user.short_description = "User"


@admin.register(ProductMetrics)
class ProductMetricsAdmin(admin.ModelAdmin):
    list_display = ('product', 'total_views', 'total_clicks', 'total_favorites',
                   'total_sales', 'total_revenue', 'last_updated')
    list_filter = ('last_updated',)
    search_fields = ('product__name',)
    readonly_fields = ('total_views', 'total_clicks', 'total_favorites', 
                      'total_cart_additions', 'total_sales', 'total_revenue',
                      'last_updated')

    fieldsets = (
        ('Product', {
            'fields': ('product',)
        }),
        ('Basic Metrics', {
            'fields': ('total_views', 'total_clicks', 'total_favorites', 
                      'total_cart_additions', 'total_sales', 'total_revenue')
        }),
        ('Timestamps', {
            'fields': ('last_updated',),
            'classes': ('collapse',)
        })
    )