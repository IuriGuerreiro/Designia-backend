from rest_framework import generics, viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.exceptions import ValidationError, PermissionDenied
from django.shortcuts import get_object_or_404
from django.db.models import Q, F, Sum
from django.db import transaction, models
from django_filters.rest_framework import DjangoFilterBackend
import logging
import json

from .models import (
    Category, Product, ProductImage, ProductReview, ProductFavorite,
    Order, OrderItem, OrderShipping, Cart, CartItem, ProductMetrics
)
from activity.models import UserClick
from .tracking_utils import track_product_listing_view, track_single_product_view, ProductTracker
from .serializers import (
    CategorySerializer, ProductListSerializer, ProductDetailSerializer,
    ProductCreateUpdateSerializer, ProductImageSerializer, ProductReviewSerializer,
    ProductFavoriteSerializer, CartSerializer, CartItemSerializer,
    OrderSerializer, OrderItemSerializer, OrderShippingSerializer, ProductMetricsSerializer
)
from .filters import ProductFilter
from .permissions import IsSellerOrReadOnly, IsOwnerOrReadOnly

# Set up logger
logger = logging.getLogger(__name__)

class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for categories - read-only operations
    """
    queryset = Category.objects.filter(is_active=True)
    serializer_class = CategorySerializer
    lookup_field = 'slug'
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'description']

    @action(detail=True, methods=['get'])
    def products(self, request, slug=None):
        """Get products in this category with view tracking"""
        category = self.get_object()
        products = Product.objects.filter(
            category=category, 
            is_active=True
        ).select_related('seller', 'category').prefetch_related('images')
        
        # Apply filtering
        filter_backend = ProductFilter()
        products = filter_backend.filter_queryset(request, products, self)
        
        # Track category views for products in this category listing
        try:
            from .tracking_utils import SessionHelper, MetricsHelper
            user, session_key = SessionHelper.get_user_or_session(request)
            
            products_list = list(products)
            
            # Ensure ProductMetrics exist for all products (bulk operation)
            logger.info(f"Ensuring ProductMetrics exist for {len(products_list)} products in category {category.name}")
            MetricsHelper.bulk_ensure_metrics(products_list)
            
            tracked_count = 0
            
            for product in products_list:
                try:
                    UserClick.track_activity(
                        product=product,
                        action='category_view',
                        user=user,
                        session_key=session_key,
                        request=request
                    )
                    tracked_count += 1
                except Exception as e:
                    logger.warning(f"Failed to track category view for product {product.id}: {str(e)}")
                    continue
            
            logger.info(f"Tracked category views for {tracked_count}/{len(products_list)} products in category {category.name}")
        except Exception as e:
            logger.error(f"Error tracking category listing views: {str(e)}")
        
        serializer = ProductListSerializer(products, many=True, context={'request': request})
        return Response(serializer.data)


class ProductViewSet(viewsets.ModelViewSet):
    """
    ViewSet for products with full CRUD operations
    """
    queryset = Product.objects.filter(is_active=True).select_related(
        'seller', 'category'
    ).prefetch_related('images', 'reviews')
    
    permission_classes = [IsAuthenticatedOrReadOnly]
    lookup_field = 'slug'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ProductFilter
    search_fields = ['name', 'description', 'brand', 'tags']
    ordering_fields = ['created_at', 'price', 'view_count', 'favorite_count']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return ProductCreateUpdateSerializer
        elif self.action == 'retrieve':
            return ProductDetailSerializer
        return ProductListSerializer

    def get_permissions(self):
        if self.action in ['update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSellerOrReadOnly()]
        return super().get_permissions()
    
    def create(self, request, *args, **kwargs):
        """Override create method"""
        serializer = self.get_serializer(data=request.data)
        
        if serializer.is_valid():
            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def perform_create(self, serializer):
        """Create a new product"""
        user = self.request.user
        product = serializer.save(seller=user)
        return product

    def list(self, request, *args, **kwargs):
        """Override list method with view tracking"""
        queryset = self.filter_queryset(self.get_queryset())
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            
            # Track views for products in this listing page
            try:
                track_product_listing_view(page, request)
            except Exception as e:
                logger.error(f"Error tracking listing views: {str(e)}")
            
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        
        # Track views for all products in non-paginated listing
        try:
            products_list = list(queryset)
            track_product_listing_view(products_list, request)
        except Exception as e:
            logger.error(f"Error tracking listing views: {str(e)}")
        
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        
        # Track view activity using tracking utils
        try:
            track_single_product_view(instance, request)
        except Exception as e:
            logger.error(f"Error tracking product view: {str(e)}")
            # Continue execution even if tracking fails
        
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def favorite(self, request, slug=None):
        """Add/remove product from favorites with activity tracking"""
        if not request.user.is_authenticated:
            return Response(
                {'detail': 'Authentication required'}, 
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        product = self.get_object()
        favorite, created = ProductFavorite.objects.get_or_create(
            user=request.user, product=product
        )
        
        if not created:
            favorite.delete()
            # Track unfavorite activity using new tracking utils
            try:
                ProductTracker.track_product_favorite(product, request.user, request, 'unfavorite')
                logger.info(f"Product unfavorite tracked: {product.name}")
            except Exception as e:
                logger.error(f"Error tracking unfavorite: {str(e)}")
            return Response({'favorited': False})
        else:
            # Track favorite activity using new tracking utils
            try:
                ProductTracker.track_product_favorite(product, request.user, request, 'favorite')
                logger.info(f"Product favorite tracked: {product.name}")
            except Exception as e:
                logger.error(f"Error tracking favorite: {str(e)}")
            return Response({'favorited': True})

    @action(detail=True, methods=['post'])
    def click(self, request, slug=None):
        """Track product clicks with activity system"""
        product = self.get_object()
        
        # Track click activity using new tracking utils
        try:
            user = request.user if request.user.is_authenticated else None
            session_key = None
            
            if not user:
                if not request.session.session_key:
                    request.session.save()
                session_key = request.session.session_key
            
            ProductTracker.track_product_click(
                product=product,
                user=user,
                session_key=session_key,
                request=request
            )
            logger.info(f"Product click tracked: {product.name}")
        except Exception as e:
            logger.error(f"Error tracking product click: {str(e)}")
        
        return Response({'clicked': True})

    @action(detail=True, methods=['get'])
    def reviews(self, request, slug=None):
        """Get product reviews"""
        product = self.get_object()
        reviews = product.reviews.filter(is_active=True).select_related('reviewer')
        serializer = ProductReviewSerializer(reviews, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def add_review(self, request, slug=None):
        """Add a review for this product"""
        product = self.get_object()
        
        # Check if user already reviewed this product
        if ProductReview.objects.filter(product=product, reviewer=request.user).exists():
            return Response(
                {'detail': 'You have already reviewed this product'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = ProductReviewSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(product=product, reviewer=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def my_products(self, request):
        """Get current user's products"""
        products = self.queryset.filter(seller=request.user)
        serializer = ProductListSerializer(products, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def favorites(self, request):
        """Get user's favorite products"""
        favorites = ProductFavorite.objects.filter(user=request.user).select_related('product')
        serializer = ProductFavoriteSerializer(favorites, many=True)
        return Response(serializer.data)


class ProductImageViewSet(viewsets.ModelViewSet):
    """
    ViewSet for product images
    """
    serializer_class = ProductImageSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrReadOnly]

    def get_queryset(self):
        product_slug = self.kwargs.get('product_slug')
        if product_slug:
            return ProductImage.objects.filter(product__slug=product_slug)
        return ProductImage.objects.none()

    def perform_create(self, serializer):
        product_slug = self.kwargs.get('product_slug')
        product = get_object_or_404(Product, slug=product_slug)
        
        # Check if user owns the product
        if product.seller != self.request.user:
            raise PermissionDenied("You can only add images to your own products")
        
        serializer.save(product=product)


class ProductReviewViewSet(viewsets.ModelViewSet):
    """
    ViewSet for product reviews
    """
    serializer_class = ProductReviewSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        # For router-based endpoints, get product from query parameter
        product_slug = self.request.query_params.get('product_slug') or self.kwargs.get('product_slug')
        if product_slug:
            return ProductReview.objects.filter(
                product__slug=product_slug, 
                is_active=True
            ).select_related('reviewer', 'product')
        return ProductReview.objects.filter(is_active=True).select_related('reviewer', 'product')

    def get_permissions(self):
        if self.action in ['update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsOwnerOrReadOnly()]
        return super().get_permissions()

    def perform_create(self, serializer):
        product_slug = self.request.data.get('product_slug') or self.request.query_params.get('product_slug') or self.kwargs.get('product_slug')
        if not product_slug:
            raise ValidationError("Product slug is required")
        product = get_object_or_404(Product, slug=product_slug)
        
        # Check if user already reviewed this product
        if ProductReview.objects.filter(product=product, reviewer=self.request.user).exists():
            raise ValidationError("You have already reviewed this product")
        
        serializer.save(product=product, reviewer=self.request.user)


class CartViewSet(viewsets.ModelViewSet):
    """
    ViewSet for shopping cart
    """
    serializer_class = CartSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        cart = Cart.get_or_create_cart(user=self.request.user)
        return cart

    def list(self, request, *args, **kwargs):
        """Get user's cart"""
        cart = Cart.get_or_create_cart(user=request.user)
        serializer = self.get_serializer(cart)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def add_item(self, request):
        """Add item to cart with comprehensive stock validation"""
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info("=== CART ADD_ITEM DEBUG START ===")
        logger.info(f"User: {request.user.username if request.user.is_authenticated else 'Anonymous'}")
        logger.info(f"Method: {request.method}")
        logger.info(f"Data: {request.data}")
        
        cart = Cart.get_or_create_cart(user=request.user)
        logger.info(f"Cart ID: {cart.id}")
        
                
        serializer = CartItemSerializer(data=request.data)
        if serializer.is_valid():
            product_id = serializer.validated_data['product_id']
            quantity = serializer.validated_data['quantity']
            
            product = get_object_or_404(Product, id=product_id, is_active=True)
            
            # Enhanced stock validation
            if not product.is_active:
                return Response(
                    {'error': 'PRODUCT_UNAVAILABLE', 'detail': 'This product is no longer available'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if product.stock_quantity <= 0:
                return Response(
                    {'error': 'OUT_OF_STOCK', 'detail': 'This product is currently out of stock'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check for concurrent cart reservations
            current_cart_quantity = CartItem.objects.filter(
                product=product
            ).aggregate(total_in_carts=models.Sum('quantity'))['total_in_carts'] or 0
            
            available_stock = product.stock_quantity - current_cart_quantity
            
            # Get or create cart item
            cart_item, item_created = CartItem.objects.get_or_create(
                cart=cart, product=product,
                defaults={'quantity': 0}  # Start with 0 to handle increment properly
            )
            
            # Calculate new quantity
            new_quantity = cart_item.quantity + quantity
            
            # Validate against available stock (excluding current cart item)
            other_carts_quantity = current_cart_quantity - cart_item.quantity
            truly_available = product.stock_quantity - other_carts_quantity
            
            if new_quantity > truly_available:
                return Response(
                    {
                        'error': 'INSUFFICIENT_STOCK',
                        'detail': f'Only {truly_available} items available in stock',
                        'available_stock': truly_available,
                        'requested_quantity': new_quantity,
                        'current_in_cart': cart_item.quantity
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Update cart item quantity
            cart_item.quantity = new_quantity
            cart_item.save()
            
            # Track cart addition activity using new tracking utils
            try:
                ProductTracker.track_cart_addition(product, request.user, quantity, request)
                logger.info(f"Cart addition tracked: {quantity}x {product.name}")
            except Exception as e:
                logger.error(f"Error tracking cart addition: {str(e)}")
            
            response_data = {
                'success': True,
                'item': CartItemSerializer(cart_item).data,
                'message': 'Item added to cart successfully' if item_created else 'Cart item quantity updated',
                'was_created': item_created
            }
            logger.info(f"Response: {response_data}")
            logger.info("=== CART ADD_ITEM DEBUG END (SUCCESS) ===")
            
            return Response(response_data, status=status.HTTP_201_CREATED if item_created else status.HTTP_200_OK)
        
        error_response = {
            'error': 'VALIDATION_ERROR',
            'detail': 'Invalid data provided',
            'errors': serializer.errors
        }
        logger.error(f"Validation errors: {serializer.errors}")
        logger.info("=== CART ADD_ITEM DEBUG END (ERROR) ===")
        
        return Response(error_response, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['patch'])
    def update_item(self, request):
        """Update cart item quantity with comprehensive stock validation"""
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info("=== CART UPDATE_ITEM DEBUG START ===")
        logger.info(f"User: {request.user.username if request.user.is_authenticated else 'Anonymous'}")
        logger.info(f"Method: {request.method}")
        logger.info(f"Data: {request.data}")
        
        cart = Cart.get_or_create_cart(user=request.user)
        logger.info(f"Cart ID: {cart.id}")
        
                
        item_id = request.data.get('item_id')
        quantity = request.data.get('quantity')
        
        if not item_id or quantity is None:
            return Response(
                {'error': 'MISSING_PARAMETERS', 'detail': 'item_id and quantity are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            quantity = int(quantity)
        except (ValueError, TypeError):
            return Response(
                {'error': 'INVALID_QUANTITY', 'detail': 'Quantity must be a valid number'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        cart_item = get_object_or_404(CartItem, id=item_id, cart=cart)
        
        if quantity <= 0:
            cart_item.delete()
            return Response({'detail': 'Item removed from cart'})
        
        # Enhanced stock validation
        product = cart_item.product
        if not product.is_active:
            return Response(
                {'error': 'PRODUCT_UNAVAILABLE', 'detail': 'This product is no longer available'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if quantity > product.stock_quantity:
            return Response(
                {
                    'error': 'INSUFFICIENT_STOCK',
                    'detail': f'Only {product.stock_quantity} items available in stock',
                    'available_stock': product.stock_quantity,
                    'requested_quantity': quantity
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check for concurrent cart updates (other users might have taken items)
        current_cart_quantity = CartItem.objects.filter(
            product=product
        ).exclude(id=cart_item.id).aggregate(
            total_in_carts=models.Sum('quantity')
        )['total_in_carts'] or 0
        
        available_for_this_cart = product.stock_quantity - current_cart_quantity
        if quantity > available_for_this_cart:
            return Response(
                {
                    'error': 'STOCK_RESERVED',
                    'detail': f'Only {available_for_this_cart} items available (some reserved in other carts)',
                    'available_stock': available_for_this_cart,
                    'requested_quantity': quantity
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        cart_item.quantity = quantity
        cart_item.save()
        
        return Response({
            'success': True,
            'item': CartItemSerializer(cart_item).data,
            'message': 'Cart item updated successfully'
        })

    @action(detail=False, methods=['delete'])
    def remove_item(self, request):
        """Remove item from cart with activity tracking"""
        cart = Cart.get_or_create_cart(user=request.user)
        
                
        item_id = request.data.get('item_id')
        
        if not item_id:
            return Response(
                {'detail': 'item_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        cart_item = get_object_or_404(CartItem, id=item_id, cart=cart)
        
        # Track cart removal activity before deleting using new tracking utils
        try:
            ProductTracker.track_cart_removal(cart_item.product, request.user, request)
            logger.info(f"Cart removal tracked: {cart_item.product.name}")
        except Exception as e:
            logger.error(f"Error tracking cart removal: {str(e)}")
        
        cart_item.delete()
        
        return Response({'detail': 'Item removed from cart'})

    @action(detail=False, methods=['delete'])
    def clear(self, request):
        """Clear all items from cart"""
        cart = Cart.get_or_create_cart(user=request.user)
        
                
        cart.items.all().delete()
        return Response({'detail': 'Cart cleared'})
    
    @action(detail=False, methods=['patch'])
    def update_item_status(self, request):
        """Update cart item status with comprehensive debugging"""
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info("=== CART UPDATE_ITEM_STATUS DEBUG START ===")
        logger.info(f"User: {request.user.username if request.user.is_authenticated else 'Anonymous'}")
        logger.info(f"Method: {request.method}")
        logger.info(f"Data: {request.data}")
        
        cart = Cart.get_or_create_cart(user=request.user)
        logger.info(f"Cart ID: {cart.id}")
        
        
        item_id = request.data.get('item_id')
        new_status = request.data.get('status')
        
        print(f"DEBUG: item_id={item_id}, new_status={new_status}")
        logger.info(f"Requested item_id: {item_id}, new_status: {new_status}")
        
        if not item_id:
            logger.error("Missing item_id parameter")
            return Response(
                {'error': 'MISSING_PARAMETERS', 'detail': 'item_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            cart_item = CartItem.objects.get(id=item_id, cart=cart)
            logger.info(f"Found cart item: {cart_item.id} - Product: {cart_item.product.name}")
            
            # For now, just return success since we don't have status field on CartItem
            # This endpoint might be used for frontend state management
            response_data = {
                'detail': 'Item status updated successfully',
                'item': {
                    'id': cart_item.id,
                    'product_name': cart_item.product.name,
                    'quantity': cart_item.quantity,
                    'status': new_status  # Echo back the requested status
                }
            }
            logger.info(f"Response: {response_data}")
            logger.info("=== CART UPDATE_ITEM_STATUS DEBUG END ===")
            
            return Response(response_data)
            
        except CartItem.DoesNotExist:
            logger.error(f"Cart item with id {item_id} not found in user's cart")
            return Response(
                {'error': 'ITEM_NOT_FOUND', 'detail': 'Item not found in cart'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            return Response(
                {'error': 'INTERNAL_ERROR', 'detail': 'An unexpected error occurred'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def validate_stock(self, request):
        """Validate stock for all cart items with comprehensive debugging"""
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info("=== CART VALIDATE_STOCK DEBUG START ===")
        logger.info(f"User: {request.user.username if request.user.is_authenticated else 'Anonymous'}")
        logger.info(f"Method: {request.method}")
        
        cart = Cart.get_or_create_cart(user=request.user)
        logger.info(f"Cart ID: {cart.id}, Total items: {cart.items.count()}")
        
        validation_results = []
        all_valid = True
        
        for item in cart.items.all():
            logger.info(f"Validating item: {item.id} - Product: {item.product.name}")
            logger.info(f"  Requested quantity: {item.quantity}")
            logger.info(f"  Available stock: {item.product.stock_quantity}")
            logger.info(f"  Product active: {item.product.is_active}")
            
            item_result = {
                'item_id': item.id,
                'product_id': str(item.product.id),
                'product_name': item.product.name,
                'requested_quantity': item.quantity,
                'available_stock': item.product.stock_quantity,
                'is_valid': True,
                'issues': []
            }
            
            # Check if product is still active
            if not item.product.is_active:
                item_result['is_valid'] = False
                item_result['issues'].append('Product is no longer available')
                all_valid = False
                logger.warning(f"  Issue: Product {item.product.name} is inactive")
            
            # Check stock availability
            if item.product.stock_quantity < item.quantity:
                item_result['is_valid'] = False
                item_result['issues'].append(f'Insufficient stock. Available: {item.product.stock_quantity}')
                all_valid = False
                logger.warning(f"  Issue: Insufficient stock for {item.product.name}")
            
            # Check if stock is zero
            if item.product.stock_quantity <= 0:
                item_result['is_valid'] = False
                item_result['issues'].append('Out of stock')
                all_valid = False
                logger.warning(f"  Issue: {item.product.name} is out of stock")
            
            validation_results.append(item_result)
            logger.info(f"  Validation result: {item_result['is_valid']}")
        
        response_data = {
            'cart_valid': all_valid,
            'total_items': len(validation_results),
            'valid_items': sum(1 for r in validation_results if r['is_valid']),
            'invalid_items': sum(1 for r in validation_results if not r['is_valid']),
            'items': validation_results
        }
        
        logger.info(f"Overall validation result: {all_valid}")
        logger.info(f"Response: {response_data}")
        logger.info("=== CART VALIDATE_STOCK DEBUG END ===")
        
        return Response(response_data)


class OrderViewSet(viewsets.ModelViewSet):
    """
    ViewSet for orders
    """
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Get orders accessible by current user (buyer orders OR orders containing user's products as seller)"""
        user = self.request.user
        
        # Get orders where user is buyer OR has items as seller
        return Order.objects.filter(
            models.Q(buyer=user) | models.Q(items__seller=user)
        ).distinct().prefetch_related('items', 'shipping_info')

    @action(detail=False, methods=['get'])
    def my_orders(self, request):
        """Get current user's orders as a buyer"""
        orders = self.get_queryset().filter(buyer=request.user)
        serializer = self.get_serializer(orders, many=True)
        return Response(serializer.data)


    @action(detail=True, methods=['patch'])
    def update_status(self, request, pk=None):
        """Update order status (for sellers/admin)"""
        from django.utils import timezone
        
        order = self.get_object()
        new_status = request.data.get('status')
        
        if not new_status:
            return Response(
                {'detail': 'Status is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if user can update this order
        if not (request.user == order.buyer or 
                order.items.filter(seller=request.user).exists() or
                request.user.is_staff):
            raise PermissionDenied("You don't have permission to update this order")
        
        # Update order status
        order.status = new_status
        
        # Automatically update timestamps based on status
        if new_status == 'shipped' and not order.shipped_at:
            order.shipped_at = timezone.now()
        elif new_status == 'delivered' and not order.delivered_at:
            order.delivered_at = timezone.now()
        
        order.save()
        
        return Response(OrderSerializer(order).data)

    @action(detail=True, methods=['patch'])
    def update_tracking(self, request, pk=None):
        """Update seller-specific tracking information with ownership verification"""
        from django.utils import timezone
        
        logger.info(f"Update tracking called for order {pk} by user {request.user.id} ({request.user.username})")
        
        try:
            order = self.get_object()
            logger.info(f"Order found: {order.id}")
        except Exception as e:
            logger.error(f"Failed to get order {pk}: {str(e)}")
            raise
        
        tracking_number = request.data.get('tracking_number')
        shipping_carrier = request.data.get('shipping_carrier', '')
        
        logger.info(f"Tracking data: number={tracking_number}, carrier={shipping_carrier}")
        
        if not tracking_number:
            return Response(
                {'detail': 'Tracking number (codigo do gajo das encomendas) is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Enhanced ownership verification - user must be seller of at least one item in the order
        user_owns_items = order.items.filter(seller=request.user).exists()
        is_staff = request.user.is_staff
        
        if not (user_owns_items or is_staff):
            logger.warning(f"User {request.user.username} attempted to update tracking for order {order.id} but owns no items in this order")
            raise PermissionDenied("You don't have permission to update tracking for this order. You must be the seller of at least one item.")
        
        # Special restriction: pending_payment orders cannot have tracking updated
        if order.status == 'pending_payment' and not is_staff:
            return Response(
                {
                    'detail': 'Cannot update tracking for orders with pending payment. Payment must be completed first.',
                    'current_status': order.status,
                    'payment_status': order.payment_status
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create or update seller-specific shipping information (only one per seller per order)
        shipping_info, created = OrderShipping.objects.get_or_create(
            order=order,
            seller=request.user,
            defaults={
                'tracking_number': tracking_number,
                'shipping_carrier': shipping_carrier,
                'shipped_at': timezone.now()
            }
        )
        
        # If updating existing shipping info
        if not created:
            logger.info(f"Updating existing tracking for seller {request.user.username} on order {order.id}")
            old_tracking = shipping_info.tracking_number
            shipping_info.tracking_number = tracking_number
            shipping_info.shipping_carrier = shipping_carrier
            if not shipping_info.shipped_at:  # Only set shipped_at if not already set
                shipping_info.shipped_at = timezone.now()
            shipping_info.save()
            logger.info(f"Tracking updated from '{old_tracking}' to '{tracking_number}'")
        
        # Check if all sellers have added tracking - if so, update order status
        sellers_with_items = order.items.values_list('seller', flat=True).distinct()
        sellers_with_tracking = order.shipping_info.values_list('seller', flat=True)
        
        if set(sellers_with_items) <= set(sellers_with_tracking):
            # All sellers have added tracking information
            if order.status in ['pending', 'confirmed', 'processing', 'payment_confirmed', 'awaiting_shipment']:
                order.status = 'shipped'
                if not order.shipped_at:
                    order.shipped_at = timezone.now()
                order.save()
        
        # Create appropriate response message
        if created:
            message = f'Tracking number {tracking_number} added successfully for your items'
            logger.info(f"New tracking created for seller {request.user.username}")
        else:
            message = f'Your tracking number updated to {tracking_number}'
            logger.info(f"Existing tracking updated for seller {request.user.username}")
        
        return Response({
            'success': True,
            'message': message,
            'is_update': not created,
            'order': OrderSerializer(order).data,
            'shipping_info': OrderShippingSerializer(shipping_info).data
        })

    @action(detail=True, methods=['get'])
    def tracking_info(self, request, pk=None):
        """Get all tracking information for an order (shows all sellers' tracking codes)"""
        order = self.get_object()
        
        # Check if user has permission to view tracking info
        is_buyer = order.buyer == request.user
        is_seller = order.items.filter(seller=request.user).exists()
        
        if not (is_buyer or is_seller or request.user.is_staff):
            raise PermissionDenied("You don't have permission to view tracking information for this order")
        
        # Get all shipping information for this order
        shipping_records = order.shipping_info.all().select_related('seller')
        
        tracking_data = []
        for shipping in shipping_records:
            # Get seller's items in this order
            seller_items = order.items.filter(seller=shipping.seller)
            
            tracking_data.append({
                'seller': {
                    'id': shipping.seller.id,
                    'username': shipping.seller.username,
                    'full_name': f"{shipping.seller.first_name} {shipping.seller.last_name}".strip()
                },
                'tracking_number': shipping.tracking_number,
                'shipping_carrier': shipping.shipping_carrier,
                'shipped_at': shipping.shipped_at,
                'item_count': seller_items.count(),
                'items_total': sum(item.total_price for item in seller_items)
            })
        
        return Response({
            'order_id': str(order.id),
            'order_status': order.status,
            'total_sellers': len(tracking_data),
            'tracking_information': tracking_data
        })

    @action(detail=False, methods=['get'])
    def seller_orders(self, request):
        """Get seller orders (orders that the current user needs to fulfill as a seller)"""
        logger.info(f"Getting seller orders for user: {request.user.id} ({request.user.username})")
        
        # Get orders where the current user is a seller of any item in the order
        # Using select_related and prefetch_related for better performance
        seller_orders = Order.objects.filter(
            items__seller=request.user
        ).distinct().select_related('buyer').prefetch_related(
            'items', 'shipping_info', 'shipping_info__seller'
        ).order_by('-created_at')
        
        logger.info(f"Found {seller_orders.count()} orders with seller items")
        
        # Apply status filtering if requested
        status_filter = request.query_params.get('status')
        if status_filter and status_filter != 'all':
            seller_orders = seller_orders.filter(status=status_filter)
        
        # Filter each order's items to show only items belonging to the current seller
        orders_data = []
        skipped_orders = 0
        
        for order in seller_orders:
            # Serialize the order
            order_data = OrderSerializer(order).data
            
            # Filter items to show only the current seller's items
            # Note: item['seller'] is an integer ID, so compare with request.user.id (also integer)
            all_sellers_in_order = [item['seller'] for item in order_data['items']]
            logger.debug(f"Order {order.id}: Looking for seller {request.user.id}, found sellers: {all_sellers_in_order}")
            
            seller_items = [
                item for item in order_data['items'] 
                if item['seller'] == request.user.id
            ]
            
            # IMPORTANT: Only include orders that actually have seller items
            # This is a safeguard to ensure sellers only see orders with their products
            if not seller_items:
                logger.warning(f"Order {order.id} has no items for seller {request.user.id}. Found sellers: {all_sellers_in_order}")
                skipped_orders += 1
                continue  # Skip this order if no items belong to the current seller
            
            order_data['items'] = seller_items
            
            # Filter shipping info to show only the current seller's shipping
            seller_shipping = [
                shipping for shipping in order_data['shipping_info']
                if shipping['seller']['id'] == request.user.id
            ]
            order_data['seller_shipping'] = seller_shipping[0] if seller_shipping else None
            
            # Update item count and potentially recalculate totals for display
            # Note: We keep the original total_amount since that's what the buyer pays
            order_data['seller_items_count'] = len(seller_items)
            order_data['seller_items_total'] = sum(float(item['total_price']) for item in seller_items)
            
            orders_data.append(order_data)
        
        logger.info(f"Returning {len(orders_data)} orders for seller {request.user.username}")
        if skipped_orders > 0:
            logger.warning(f"Skipped {skipped_orders} orders with no seller items - this indicates a data issue")
        
        return Response(orders_data)

    @action(detail=True, methods=['patch'])
    def cancel_order(self, request, pk=None):
        """Cancel an order with reason (for sellers)"""
        from django.utils import timezone
        
        order = self.get_object()
        cancellation_reason = request.data.get('cancellation_reason', '')
        
        if not cancellation_reason:
            return Response(
                {'detail': 'Cancellation reason is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if user can cancel this order (seller or staff)
        if not (order.items.filter(seller=request.user).exists() or request.user.is_staff):
            raise PermissionDenied("You don't have permission to cancel this order")
        
        # Check if order can be cancelled
        if order.status not in ['pending', 'confirmed']:
            return Response(
                {'detail': f'Order cannot be cancelled. Current status: {order.status}. Orders can only be cancelled when pending or confirmed.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Cancel the order
        order.status = 'cancelled'
        order.cancellation_reason = cancellation_reason
        order.cancelled_by = request.user
        order.cancelled_at = timezone.now()
        order.save()
        
        return Response({
            'success': True,
            'message': 'Order cancelled successfully',
            'order': OrderSerializer(order).data
        })

    @action(detail=True, methods=['patch'])
    def process_order(self, request, pk=None):
        """Move order from payment_confirmed to awaiting_shipment status (for sellers)"""
        from django.utils import timezone
        
        order = self.get_object()
        
        # Check if user can process this order (seller or staff)
        if not (order.items.filter(seller=request.user).exists() or request.user.is_staff):
            raise PermissionDenied("You don't have permission to process this order")
        
        # Check if order can be processed
        if order.status not in ['payment_confirmed', 'pending', 'confirmed']:  # Include legacy statuses
            return Response(
                {'detail': f'Order cannot be processed. Current status: {order.status}. Only payment confirmed orders can be processed.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check payment status
        if order.payment_status != 'paid':
            return Response(
                {'detail': f'Order must be paid before processing. Current payment status: {order.payment_status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Process the order - move to awaiting_shipment
        order.status = 'awaiting_shipment'
        order.save()
        
        return Response({
            'success': True,
            'message': 'Order moved to awaiting shipment successfully',
            'order': OrderSerializer(order).data
        })

    @action(detail=True, methods=['patch'])
    def update_order_status(self, request, pk=None):
        """Update order status with proper validations for payment and ownership"""
        from django.utils import timezone
        
        order = self.get_object()
        new_status = request.data.get('status')
        
        if not new_status:
            return Response(
                {'detail': 'Status is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Valid status transitions
        valid_statuses = ['pending', 'confirmed', 'awaiting_shipment', 'shipped', 'delivered', 'cancelled', 'refunded']
        if new_status not in valid_statuses:
            return Response(
                {'detail': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if user owns at least one item in the order (seller verification)
        user_owns_items = order.items.filter(seller=request.user).exists()
        is_buyer = order.buyer == request.user
        is_staff = request.user.is_staff
        
        if not (user_owns_items or is_buyer or is_staff):
            raise PermissionDenied("You don't have permission to update this order. You must be the seller of at least one item.")
        
        # Special restriction: pending_payment orders cannot be manually updated
        if order.status == 'pending_payment' and not is_staff:
            return Response(
                {
                    'detail': 'Orders with pending payment status cannot be manually updated. Payment must be completed first.',
                    'current_status': order.status,
                    'payment_status': order.payment_status
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Status transition validations
        current_status = order.status
        
        # Define valid transitions based on business logic
        valid_transitions = {
            'pending_payment': [],  # Cannot be manually changed - only Stripe webhook can update
            'payment_confirmed': ['awaiting_shipment', 'cancelled'],  # Can go directly to awaiting shipment or cancel
            'awaiting_shipment': ['shipped', 'cancelled'],
            'shipped': ['delivered'],
            'delivered': [],  # Final status
            'cancelled': [],  # Final status
            'refunded': [],   # Final status
            # Handle legacy edge cases
            'paid': ['awaiting_shipment', 'cancelled'],  # Legacy compatibility
            'pending': ['payment_confirmed', 'awaiting_shipment', 'cancelled'],  # Legacy compatibility
            'confirmed': ['awaiting_shipment', 'cancelled'],  # Legacy compatibility
            'processing': ['awaiting_shipment', 'cancelled']  # Legacy compatibility
        }
        
        if new_status not in valid_transitions.get(current_status, []):
            return Response(
                {
                    'detail': f'Invalid status transition from {current_status} to {new_status}',
                    'current_status': current_status,
                    'allowed_transitions': valid_transitions.get(current_status, [])
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Enhanced validations for specific transitions with payment status checks
        
        # For awaiting_shipment status: must be paid and from payment_confirmed
        if new_status == 'awaiting_shipment':
            if order.payment_status != 'paid':
                return Response(
                    {'detail': f'Order must be paid before awaiting shipment. Current payment status: {order.payment_status}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if current_status not in ['payment_confirmed', 'pending', 'confirmed', 'processing', 'paid']:  # Include legacy statuses
                return Response(
                    {'detail': f'Orders can only be moved to awaiting shipment from payment confirmed status. Current status: {current_status}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # For shipped status: must be paid and from awaiting_shipment
        if new_status == 'shipped':
            if order.payment_status != 'paid':
                return Response(
                    {'detail': f'Order must be paid before shipping. Current payment status: {order.payment_status}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if current_status != 'awaiting_shipment':
                return Response(
                    {'detail': f'Orders can only be shipped from awaiting shipment status. Current status: {current_status}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # For delivered status: must be paid and from shipped status only
        if new_status == 'delivered':
            if order.payment_status != 'paid':
                return Response(
                    {'detail': f'Order must be paid before delivery confirmation. Current payment status: {order.payment_status}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if current_status != 'shipped':
                return Response(
                    {'detail': f'Orders can only be delivered from shipped status. Current status: {current_status}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Permission checks for specific actions
        
        # Only sellers can move to awaiting_shipment/shipped (fulfillment actions)
        if new_status in ['awaiting_shipment', 'shipped'] and not (user_owns_items or is_staff):
            raise PermissionDenied("Only sellers can move orders to awaiting shipment or shipped status")
        
        # Only buyers or staff can confirm delivery
        if new_status == 'delivered' and not (is_buyer or is_staff):
            raise PermissionDenied("Only buyers can confirm delivery")
        
        # Sellers and buyers can cancel (with different rules)
        if new_status == 'cancelled':
            if current_status in ['shipped', 'delivered']:
                raise PermissionDenied("Cannot cancel orders that have been shipped or delivered")
        
        # Update the order status
        old_status = order.status
        order.status = new_status
        
        # Update timestamps based on status
        if new_status == 'shipped' and not order.shipped_at:
            order.shipped_at = timezone.now()
        elif new_status == 'delivered' and not order.delivered_at:
            order.delivered_at = timezone.now()
        elif new_status == 'cancelled' and not order.cancelled_at:
            order.cancelled_at = timezone.now()
            order.cancelled_by = request.user
        
        order.save()
        
        # Log the status change
        logger.info(f"Order {order.id} status updated from {old_status} to {new_status} by user {request.user.username}")
        
        return Response({
            'success': True,
            'message': f'Order status updated from {old_status} to {new_status}',
            'order': OrderSerializer(order).data,
            'previous_status': old_status,
            'new_status': new_status
        })

    @action(detail=True, methods=['patch'])
    def update_carrier_code(self, request, pk=None):
        """Update carrier code for processing orders (for sellers)"""
        order = self.get_object()
        carrier_code = request.data.get('carrier_code', '')
        shipping_carrier = request.data.get('shipping_carrier', '')
        
        if not carrier_code:
            return Response(
                {'detail': 'Carrier code is required (e.g., CTT DY08912401385471)'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if user can update this order (seller or staff)
        if not (order.items.filter(seller=request.user).exists() or request.user.is_staff):
            raise PermissionDenied("You don't have permission to update this order")
        
        # Check if order is in appropriate status for carrier code
        if order.status not in ['awaiting_shipment', 'payment_confirmed', 'confirmed']:
            return Response(
                {'detail': f'Carrier codes can only be added to orders awaiting shipment or confirmed orders. Current status: {order.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update carrier code
        order.carrier_code = carrier_code
        if shipping_carrier:
            order.shipping_carrier = shipping_carrier
        order.save()
        
        return Response({
            'success': True,
            'message': f'Carrier code {carrier_code} added successfully',
            'order': OrderSerializer(order).data
        })


class ProductMetricsViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for product metrics - read-only for sellers
    """
    serializer_class = ProductMetricsSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ProductMetrics.objects.filter(product__seller=self.request.user)

    @action(detail=False, methods=['get'])
    def dashboard_metrics(self, request):
        """
        Get comprehensive metrics for seller dashboard
        """
        user = request.user
        
        # Product metrics for the seller
        product_metrics = ProductMetrics.objects.filter(product__seller=user).aggregate(
            total_views=Sum('total_views'),
            total_clicks=Sum('total_clicks'),
            total_favorites=Sum('total_favorites'),
            total_cart_additions=Sum('total_cart_additions'),
            total_sales=Sum('total_sales'),
            total_revenue=Sum('total_revenue')
        )
        
        # Product counts
        product_counts = Product.objects.filter(seller=user).aggregate(
            total_products=models.Count('id'),
            active_products=models.Count('id', filter=Q(is_active=True)),
            featured_products=models.Count('id', filter=Q(is_featured=True))
        )
        
        # Category count
        category_count = Category.objects.filter(
            products__seller=user, 
            products__is_active=True
        ).distinct().count()
        
        # Recent orders for seller's products
        recent_orders = OrderItem.objects.filter(
            seller=user
        ).select_related(
            'order', 'product'
        ).order_by('-order__created_at')[:10]
        
        # Serialize order data
        orders_data = []
        for order_item in recent_orders:
            orders_data.append({
                'id': str(order_item.order.id),
                'customer': f"{order_item.order.buyer.first_name} {order_item.order.buyer.last_name}" or order_item.order.buyer.username,
                'date': order_item.order.created_at.strftime('%Y-%m-%d'),
                'product_name': order_item.product_name,
                'quantity': order_item.quantity,
                'total_price': str(order_item.total_price),
                'status': order_item.order.status,
                'shipping_address': order_item.order.shipping_address.get('address', 'N/A') if order_item.order.shipping_address else 'N/A'
            })
        
        # Compile dashboard data
        dashboard_data = {
            'product_metrics': {
                'total_views': product_metrics['total_views'] or 0,
                'total_clicks': product_metrics['total_clicks'] or 0,
                'total_favorites': product_metrics['total_favorites'] or 0,
                'total_cart_additions': product_metrics['total_cart_additions'] or 0,
                'total_sales': product_metrics['total_sales'] or 0,
                'total_revenue': str(product_metrics['total_revenue'] or 0),
                'wishlist_adds': product_metrics['total_favorites'] or 0,  # Alias for favorites
                'cart_adds': product_metrics['total_cart_additions'] or 0,  # Alias for cart additions
                'sales': product_metrics['total_sales'] or 0,  # Alias for sales
                'revenue': str(product_metrics['total_revenue'] or 0),  # Alias for revenue
                'views': product_metrics['total_views'] or 0,  # Alias for views
                'clicks': product_metrics['total_clicks'] or 0,  # Alias for clicks
            },
            'product_counts': {
                'total_products': product_counts['total_products'] or 0,
                'active_listings': product_counts['active_products'] or 0,
                'featured_products': product_counts['featured_products'] or 0,
                'total_categories': category_count
            },
            'recent_orders': orders_data
        }
        
        return Response(dashboard_data)

    @action(detail=False, methods=['get'], url_path='product_metrics/(?P<product_slug>[^/.]+)')
    def product_metrics(self, request, product_slug=None):
        """
        Get metrics for a specific product by slug
        """
        user = request.user
        
        try:
            # Get the product by slug and ensure it belongs to the current user
            product = Product.objects.get(slug=product_slug, seller=user)
        except Product.DoesNotExist:
            return Response(
                {'error': 'Product not found or you do not have permission to view its metrics'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get or create product metrics
        product_metrics, created = ProductMetrics.objects.get_or_create(
            product=product,
            defaults={
                'total_views': 0,
                'total_clicks': 0,
                'total_favorites': 0,
                'total_cart_additions': 0,
                'total_sales': 0,
                'total_revenue': 0,
            }
        )
        
        # Get recent orders for this specific product only
        recent_orders = OrderItem.objects.filter(
            product=product,
            seller=user
        ).select_related(
            'order', 'product'
        ).order_by('-order__created_at')[:10]
        
        # Serialize order data
        orders_data = []
        for order_item in recent_orders:
            orders_data.append({
                'id': str(order_item.order.id),
                'customer': f"{order_item.order.buyer.first_name} {order_item.order.buyer.last_name}" or order_item.order.buyer.username,
                'date': order_item.order.created_at.strftime('%Y-%m-%d'),
                'product_name': order_item.product_name,
                'quantity': order_item.quantity,
                'total_price': str(order_item.total_price),
                'status': order_item.order.status,
                'shipping_address': order_item.order.shipping_address.get('address', 'N/A') if order_item.order.shipping_address else 'N/A'
            })
        
        # Compile product-specific data
        product_data = {
            'product_info': {
                'id': str(product.id),
                'name': product.name,
                'slug': product.slug,
                'price': str(product.price),
                'stock_quantity': product.stock_quantity,
                'is_active': product.is_active,
                'created_at': product.created_at.strftime('%Y-%m-%d'),
            },
            'product_metrics': {
                'total_views': product_metrics.total_views,
                'total_clicks': product_metrics.total_clicks,
                'total_favorites': product_metrics.total_favorites,
                'total_cart_additions': product_metrics.total_cart_additions,
                'total_sales': product_metrics.total_sales,
                'total_revenue': str(product_metrics.total_revenue),
                'wishlist_adds': product_metrics.total_favorites,  # Alias for favorites
                'cart_adds': product_metrics.total_cart_additions,  # Alias for cart additions
                'sales': product_metrics.total_sales,  # Alias for sales
                'revenue': str(product_metrics.total_revenue),  # Alias for revenue
                'views': product_metrics.total_views,  # Alias for views
                'clicks': product_metrics.total_clicks,  # Alias for clicks
            },
            'product_counts': {
                'total_products': 1,  # This is for a single product
                'active_listings': 1 if product.is_active else 0,
                'featured_products': 1 if product.is_featured else 0,
                'total_categories': 1
            },
            'recent_orders': orders_data
        }
        
        return Response(product_data)