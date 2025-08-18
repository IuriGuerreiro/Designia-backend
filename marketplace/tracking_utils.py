"""
Tracking utilities for marketplace activities.

This module provides centralized functions for tracking user activities
such as views, clicks, purchases, favorites, cart interactions, and more.
All tracking functions automatically update ProductMetrics.
"""

import logging
from typing import Optional, Union, List
from django.contrib.auth import get_user_model
from django.http import HttpRequest
from django.db import transaction, models
from django.utils import timezone
from activity.models import UserClick

# Import transaction utilities
from utils.transaction_utils import atomic_with_isolation

User = get_user_model()
logger = logging.getLogger(__name__)


class ProductTracker:
    """
    Centralized product tracking utilities.
    
    This class provides static methods for tracking various user interactions
    with products, including views, clicks, purchases, and other activities.
    """
    
    @staticmethod
    def track_product_view(product, user: Optional[User] = None, 
                          session_key: Optional[str] = None, 
                          request: Optional[HttpRequest] = None) -> UserClick:
        """
        Track when a user views a product.
        Automatically ensures ProductMetrics exists for the product.
        
        Args:
            product: Product instance
            user: User instance (None for anonymous users)
            session_key: Session key for anonymous tracking
            request: HTTP request for metadata extraction
            
        Returns:
            UserClick: Created activity record
        """
        try:
            # Ensure ProductMetrics exists for this product
            MetricsHelper.ensure_metrics_exist(product)
            
            activity = UserClick.track_activity(
                product=product,
                action='detail_view',
                user=user,
                session_key=session_key,
                request=request
            )
            logger.info(f"Product view tracked: {product.name} by {user or session_key}")
            return activity
        except Exception as e:
            logger.error(f"Error tracking product view for {product.name}: {str(e)}")
            raise
    
    @staticmethod
    def track_product_click(product, user: Optional[User] = None,
                           session_key: Optional[str] = None,
                           request: Optional[HttpRequest] = None) -> UserClick:
        """
        Track when a user clicks on a product.
        Automatically ensures ProductMetrics exists for the product.
        
        Args:
            product: Product instance
            user: User instance (None for anonymous users)
            session_key: Session key for anonymous tracking
            request: HTTP request for metadata extraction
            
        Returns:
            UserClick: Created activity record
        """
        try:
            # Ensure ProductMetrics exists for this product
            MetricsHelper.ensure_metrics_exist(product)
            
            activity = UserClick.track_activity(
                product=product,
                action='click',
                user=user,
                session_key=session_key,
                request=request
            )
            logger.info(f"Product click tracked: {product.name} by {user or session_key}")
            return activity
        except Exception as e:
            logger.error(f"Error tracking product click for {product.name}: {str(e)}")
            raise
    
    @staticmethod
    def track_product_favorite(product, user: User, 
                              request: Optional[HttpRequest] = None,
                              action: str = 'favorite') -> UserClick:
        """
        Track when a user adds/removes a product to/from favorites.
        Automatically ensures ProductMetrics exists for the product.
        
        Args:
            product: Product instance
            user: User instance (required for favorites)
            request: HTTP request for metadata extraction
            action: 'favorite' or 'unfavorite'
            
        Returns:
            UserClick: Created activity record
        """
        if not user:
            raise ValueError("User is required for favorite tracking")
            
        try:
            # Ensure ProductMetrics exists for this product
            MetricsHelper.ensure_metrics_exist(product)
            
            activity = UserClick.track_activity(
                product=product,
                action=action,
                user=user,
                request=request
            )
            logger.info(f"Product {action} tracked: {product.name} by {user.username}")
            return activity
        except Exception as e:
            logger.error(f"Error tracking product {action} for {product.name}: {str(e)}")
            raise
    
    @staticmethod
    def track_cart_addition(product, user: User, quantity: int = 1,
                           request: Optional[HttpRequest] = None) -> UserClick:
        """
        Track when a user adds a product to their cart.
        Automatically ensures ProductMetrics exists for the product.
        
        Args:
            product: Product instance
            user: User instance (required for cart)
            quantity: Quantity added to cart
            request: HTTP request for metadata extraction
            
        Returns:
            UserClick: Created activity record
        """
        if not user:
            raise ValueError("User is required for cart tracking")
            
        try:
            # Ensure ProductMetrics exists for this product
            MetricsHelper.ensure_metrics_exist(product)
            
            activity = UserClick.track_activity(
                product=product,
                action='cart_add',
                user=user,
                request=request
            )
            logger.info(f"Cart addition tracked: {quantity}x {product.name} by {user.username}")
            return activity
        except Exception as e:
            logger.error(f"Error tracking cart addition for {product.name}: {str(e)}")
            raise
    
    @staticmethod
    def track_cart_removal(product, user: User,
                          request: Optional[HttpRequest] = None) -> UserClick:
        """
        Track when a user removes a product from their cart.
        Automatically ensures ProductMetrics exists for the product.
        
        Args:
            product: Product instance
            user: User instance (required for cart)
            request: HTTP request for metadata extraction
            
        Returns:
            UserClick: Created activity record
        """
        if not user:
            raise ValueError("User is required for cart tracking")
            
        try:
            # Ensure ProductMetrics exists for this product
            MetricsHelper.ensure_metrics_exist(product)
            
            activity = UserClick.track_activity(
                product=product,
                action='cart_remove',
                user=user,
                request=request
            )
            logger.info(f"Cart removal tracked: {product.name} by {user.username}")
            return activity
        except Exception as e:
            logger.error(f"Error tracking cart removal for {product.name}: {str(e)}")
            raise
    
    @staticmethod
    def track_product_purchase(product, user: User, quantity: int, 
                              order_amount: Union[int, float],
                              request: Optional[HttpRequest] = None) -> bool:
        """
        Track when a user purchases a product.
        
        This updates product metrics with sales data.
        
        Args:
            product: Product instance
            user: User instance (required for purchases)
            quantity: Quantity purchased
            order_amount: Total order amount for this product
            request: HTTP request for metadata extraction
            
        Returns:
            bool: True if tracking successful
        """
        if not user:
            raise ValueError("User is required for purchase tracking")
            
        try:
            from marketplace.models import ProductMetrics
            from decimal import Decimal
            
            # Update product metrics for purchase
            with atomic_with_isolation('REPEATABLE READ'):
                metrics, created = ProductMetrics.objects.get_or_create(
                    product=product,
                    defaults={
                        'total_views': 0,
                        'total_clicks': 0,
                        'total_favorites': 0,
                        'total_cart_additions': 0,
                        'total_sales': 0,
                        'total_revenue': Decimal('0.00'),
                    }
                )
                
                # Update sales metrics
                metrics.total_sales += quantity
                metrics.total_revenue += Decimal(str(order_amount))
                metrics.save()
                
            logger.info(f"Purchase tracked: {quantity}x {product.name} "
                       f"(${order_amount}) by {user.username}")
            return True
            
        except Exception as e:
            logger.error(f"Error tracking purchase for {product.name}: {str(e)}")
            raise
    
    @staticmethod
    def track_listing_views(products: List, user: Optional[User] = None,
                           session_key: Optional[str] = None,
                           request: Optional[HttpRequest] = None) -> int:
        """
        Track views for multiple products in a listing/search result.
        Automatically ensures ProductMetrics exist for all products.
        
        This is used when a user views a product listing page, registering
        views for all products shown in the listing.
        
        Args:
            products: List of Product instances
            user: User instance (None for anonymous users)
            session_key: Session key for anonymous tracking  
            request: HTTP request for metadata extraction
            
        Returns:
            int: Number of products successfully tracked
        """
        tracked_count = 0
        
        try:
            # Ensure ProductMetrics exist for all products (bulk operation)
            logger.info(f"Ensuring ProductMetrics exist for {len(products)} products")
            MetricsHelper.bulk_ensure_metrics(products)
            
            # Get or ensure session key for anonymous users
            if not user and not session_key and request:
                if not request.session.session_key:
                    request.session.save()
                session_key = request.session.session_key
            
            # Track listing view for each product in the listing
            for product in products:
                try:
                    UserClick.track_activity(
                        product=product,
                        action='listing_view',
                        user=user,
                        session_key=session_key,
                        request=request
                    )
                    tracked_count += 1
                except Exception as e:
                    logger.warning(f"Failed to track view for product {product.id}: {str(e)}")
                    continue
            
            logger.info(f"Listing views tracked: {tracked_count}/{len(products)} products")
            return tracked_count
            
        except Exception as e:
            logger.error(f"Error tracking listing views: {str(e)}")
            return tracked_count


class MetricsHelper:
    """
    Helper class for working with product metrics and analytics.
    """
    
    @staticmethod
    def get_or_create_metrics(product):
        """
        Get or create ProductMetrics instance for a product.
        
        Args:
            product: Product instance
            
        Returns:
            tuple: (ProductMetrics instance, created boolean)
        """
        from marketplace.models import ProductMetrics
        from decimal import Decimal
        
        try:
            metrics, created = ProductMetrics.objects.get_or_create(
                product=product,
                defaults={
                    'total_views': 0,
                    'total_clicks': 0,
                    'total_favorites': 0,
                    'total_cart_additions': 0,
                    'total_sales': 0,
                    'total_revenue': Decimal('0.00'),
                }
            )
            
            if created:
                logger.info(f"Created new ProductMetrics for product: {product.name}")
            
            return metrics, created
            
        except Exception as e:
            logger.error(f"Error creating ProductMetrics for product {product.name}: {str(e)}")
            raise
    
    @staticmethod
    def ensure_metrics_exist(product):
        """
        Ensure ProductMetrics exists for a product, creating if necessary.
        
        Args:
            product: Product instance
            
        Returns:
            ProductMetrics: The metrics instance (guaranteed to exist)
        """
        metrics, created = MetricsHelper.get_or_create_metrics(product)
        return metrics
    
    @staticmethod
    def bulk_ensure_metrics(products: List):
        """
        Ensure ProductMetrics exist for multiple products, creating as needed.
        
        Args:
            products: List of Product instances
            
        Returns:
            dict: {product_id: ProductMetrics instance}
        """
        from marketplace.models import ProductMetrics
        from decimal import Decimal
        
        metrics_dict = {}
        products_needing_metrics = []
        
        try:
            # First, get existing metrics
            existing_metrics = ProductMetrics.objects.filter(
                product__in=products
            ).select_related('product')
            
            # Create dict of existing metrics
            for metric in existing_metrics:
                metrics_dict[metric.product.id] = metric
            
            # Find products that need metrics created
            for product in products:
                if product.id not in metrics_dict:
                    products_needing_metrics.append(product)
            
            # Bulk create missing metrics
            if products_needing_metrics:
                new_metrics = []
                for product in products_needing_metrics:
                    new_metrics.append(ProductMetrics(
                        product=product,
                        total_views=0,
                        total_clicks=0,
                        total_favorites=0,
                        total_cart_additions=0,
                        total_sales=0,
                        total_revenue=Decimal('0.00'),
                    ))
                
                # Bulk create new metrics
                created_metrics = ProductMetrics.objects.bulk_create(
                    new_metrics, 
                    ignore_conflicts=True
                )
                
                logger.info(f"Bulk created ProductMetrics for {len(created_metrics)} products")
                
                # Add newly created metrics to dict
                for metric in created_metrics:
                    metrics_dict[metric.product.id] = metric
            
            return metrics_dict
            
        except Exception as e:
            logger.error(f"Error in bulk_ensure_metrics: {str(e)}")
            # Fallback to individual creation
            for product in products:
                try:
                    metrics, _ = MetricsHelper.get_or_create_metrics(product)
                    metrics_dict[product.id] = metrics
                except Exception as product_error:
                    logger.error(f"Failed to create metrics for product {product.id}: {str(product_error)}")
                    
            return metrics_dict
    
    @staticmethod
    def bulk_update_metrics(products: List) -> int:
        """
        Bulk update metrics for multiple products.
        
        This recalculates metrics from UserClick activities.
        
        Args:
            products: List of Product instances
            
        Returns:
            int: Number of products updated
        """
        updated_count = 0
        
        try:
            for product in products:
                try:
                    metrics, _ = MetricsHelper.get_or_create_metrics(product)
                    
                    # Recalculate metrics from UserClick activities
                    activities = UserClick.objects.filter(product=product)
                    
                    metrics.total_views = activities.filter(action='view').count()
                    # Total clicks includes both 'click' actions and 'cart_add' actions (since cart addition is a click interaction)
                    metrics.total_clicks = activities.filter(action__in=['click', 'cart_add']).count()
                    metrics.total_favorites = activities.filter(action='favorite').count()
                    metrics.total_cart_additions = activities.filter(action='cart_add').count()
                    
                    metrics.save()
                    updated_count += 1
                    
                except Exception as e:
                    logger.warning(f"Failed to update metrics for product {product.id}: {str(e)}")
                    continue
            
            logger.info(f"Bulk metrics update: {updated_count}/{len(products)} products")
            return updated_count
            
        except Exception as e:
            logger.error(f"Error in bulk metrics update: {str(e)}")
            return updated_count


class SessionHelper:
    """
    Helper class for managing session-based tracking.
    """
    
    @staticmethod
    def ensure_session_key(request: HttpRequest) -> Optional[str]:
        """
        Ensure request has a session key for anonymous tracking.
        
        Args:
            request: HTTP request
            
        Returns:
            str: Session key or None if error
        """
        try:
            if not request.session.session_key:
                request.session.save()
            return request.session.session_key
        except Exception as e:
            logger.error(f"Error ensuring session key: {str(e)}")
            return None
    
    @staticmethod
    def get_user_or_session(request: HttpRequest) -> tuple:
        """
        Get user and session information from request.
        
        Args:
            request: HTTP request
            
        Returns:
            tuple: (user or None, session_key or None)
        """
        user = request.user if request.user.is_authenticated else None
        session_key = None
        
        if not user:
            session_key = SessionHelper.ensure_session_key(request)
        
        return user, session_key


# Convenience functions for common tracking scenarios
def track_product_listing_view(products: List, request: HttpRequest) -> int:
    """
    Convenience function to track listing views.
    
    Args:
        products: List of products shown in listing
        request: HTTP request
        
    Returns:
        int: Number of products tracked
    """
    user, session_key = SessionHelper.get_user_or_session(request)
    return ProductTracker.track_listing_views(
        products=products,
        user=user,
        session_key=session_key,
        request=request
    )


def track_single_product_view(product, request: HttpRequest) -> UserClick:
    """
    Convenience function to track single product view.
    
    Args:
        product: Product instance
        request: HTTP request
        
    Returns:
        UserClick: Activity record
    """
    user, session_key = SessionHelper.get_user_or_session(request)
    return ProductTracker.track_product_view(
        product=product,
        user=user,
        session_key=session_key,
        request=request
    )