from django.contrib import admin
from .models import UserClick, ActivitySummary


@admin.register(UserClick)
class UserClickAdmin(admin.ModelAdmin):
    list_display = ['product', 'action', 'user', 'session_key', 'ip_address', 'created_at']
    list_filter = ['action', 'created_at', 'product__category']
    search_fields = ['product__name', 'user__username', 'user__email', 'session_key', 'ip_address']
    readonly_fields = ['created_at']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Activity Information', {
            'fields': ('product', 'action', 'user', 'session_key')
        }),
        ('Request Metadata', {
            'fields': ('ip_address', 'user_agent', 'referer'),
            'classes': ['collapse']
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ['collapse']
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('product', 'user')


@admin.register(ActivitySummary)
class ActivitySummaryAdmin(admin.ModelAdmin):
    list_display = [
        'product', 'period_type', 'period_start', 'period_end',
        'total_views', 'total_clicks', 'total_favorites', 'total_cart_additions',
        'unique_users', 'unique_sessions'
    ]
    list_filter = ['period_type', 'period_start', 'product__category']
    search_fields = ['product__name']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'period_start'
    
    fieldsets = (
        ('Summary Information', {
            'fields': ('product', 'period_type', 'period_start', 'period_end')
        }),
        ('Activity Metrics', {
            'fields': (
                'total_views', 'total_clicks', 'total_favorites', 'total_unfavorites',
                'total_cart_additions', 'total_cart_removals'
            )
        }),
        ('Unique Metrics', {
            'fields': ('unique_users', 'unique_sessions')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ['collapse']
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('product')