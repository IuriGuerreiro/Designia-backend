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
    Order, OrderItem, Cart, CartItem, ProductMetrics
)
from activity.models import UserClick
from .serializers import (
    CategorySerializer, ProductListSerializer, ProductDetailSerializer,
    ProductCreateUpdateSerializer, ProductImageSerializer, ProductReviewSerializer,
    ProductFavoriteSerializer, CartSerializer, CartItemSerializer,
    OrderSerializer, OrderItemSerializer, ProductMetricsSerializer
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
        """Get products in this category"""
        category = self.get_object()
        products = Product.objects.filter(
            category=category, 
            is_active=True
        ).select_related('seller', 'category').prefetch_related('images')
        
        # Apply filtering
        filter_backend = ProductFilter()
        products = filter_backend.filter_queryset(request, products, self)
        
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
        """Override create to add debug logging"""
        logger.info("=== PRODUCT CREATE REQUEST START ===")
        logger.info(f"User: {request.user} (authenticated: {request.user.is_authenticated})")
        logger.info(f"Content-Type: {request.content_type}")
        logger.info(f"Request method: {request.method}")
        
        # Get serializer and validate
        serializer = self.get_serializer(data=request.data)
        
        logger.info(f"Serializer: {type(serializer).__name__}")
        logger.info(f"Initial data keys: {list(request.data.keys()) if hasattr(request.data, 'keys') else 'No keys method'}")
        
        if serializer.is_valid():
            logger.info("Serializer validation passed, calling perform_create...")
            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)
            logger.info("=== PRODUCT CREATE REQUEST SUCCESS ===")
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        else:
            logger.error("=== PRODUCT CREATE REQUEST - VALIDATION FAILED ===")
            logger.error(f"Serializer errors: {serializer.errors}")
            logger.error(f"Non-field errors: {serializer.non_field_errors if hasattr(serializer, 'non_field_errors') else 'None'}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def perform_create(self, serializer):
        """Create a new product with extensive debugging"""
        logger.info("=== PRODUCT CREATE DEBUG START ===")
        
        # Debug user info
        user = self.request.user
        logger.info(f"User: {user.email} (ID: {user.id})")
        logger.info(f"User is authenticated: {user.is_authenticated}")
        logger.info(f"User is seller: {getattr(user, 'is_seller', 'No is_seller field')}")
        
        # Debug request data
        logger.info(f"Request method: {self.request.method}")
        logger.info(f"Request content type: {self.request.content_type}")
        
        # Debug POST data
        if hasattr(self.request, 'POST'):
            logger.info(f"POST data: {dict(self.request.POST)}")
        
        # Debug FILES data
        if hasattr(self.request, 'FILES'):
            logger.info(f"FILES data: {dict(self.request.FILES)}")
            for key, file in self.request.FILES.items():
                logger.info(f"File {key}: {file.name} ({file.size} bytes)")
        
        # Debug raw data
        if hasattr(self.request, 'data'):
            logger.info(f"Request data keys: {list(self.request.data.keys())}")
            # Log non-file data safely
            safe_data = {}
            for key, value in self.request.data.items():
                if hasattr(value, 'read'):  # File-like object
                    safe_data[key] = f"<File: {getattr(value, 'name', 'unknown')}>"
                else:
                    safe_data[key] = value
            logger.info(f"Request data (safe): {safe_data}")
        
        # Debug serializer validation
        logger.info(f"Serializer class: {serializer.__class__.__name__}")
        logger.info(f"Serializer is valid: {serializer.is_valid()}")
        
        if not serializer.is_valid():
            logger.error(f"Serializer errors: {serializer.errors}")
            logger.error("=== PRODUCT CREATE DEBUG - VALIDATION FAILED ===")
            raise ValidationError(serializer.errors)
        
        logger.info(f"Validated data keys: {list(serializer.validated_data.keys())}")
        
        # Safe logging of validated data (excluding files)
        safe_validated_data = {}
        for key, value in serializer.validated_data.items():
            if hasattr(value, 'read'):  # File-like object
                safe_validated_data[key] = f"<File: {getattr(value, 'name', 'unknown')}>"
            else:
                safe_validated_data[key] = value
        logger.info(f"Validated data (safe): {safe_validated_data}")
        
        try:
            # Save the product
            logger.info("Attempting to save product...")
            product = serializer.save(seller=user)
            logger.info(f"Product created successfully with ID: {product.id}, slug: {product.slug}")
            logger.info("=== PRODUCT CREATE DEBUG - SUCCESS ===")
            return product
            
        except Exception as e:
            logger.error(f"Error saving product: {str(e)}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error("=== PRODUCT CREATE DEBUG - SAVE FAILED ===")
            raise

    def list(self, request, *args, **kwargs):
        """Override list method with debugging"""
        logger.info("=== PRODUCT LIST REQUEST START ===")
        logger.info(f"User: {request.user} (authenticated: {request.user.is_authenticated})")
        logger.info(f"Query params: {dict(request.GET)}")
        
        queryset = self.filter_queryset(self.get_queryset())
        logger.info(f"Filtered queryset count: {queryset.count()}")
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            logger.info(f"Paginated to {len(page)} items")
            serializer = self.get_serializer(page, many=True)
            logger.info(f"Serialized data length: {len(serializer.data)}")
            logger.info("=== PRODUCT LIST REQUEST SUCCESS (PAGINATED) ===")
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        logger.info(f"Serialized data length: {len(serializer.data)}")
        logger.info("=== PRODUCT LIST REQUEST SUCCESS ===")
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        """Override retrieve method with activity tracking"""
        logger.info("=== PRODUCT RETRIEVE REQUEST START ===")
        logger.info(f"User: {request.user} (authenticated: {request.user.is_authenticated})")
        logger.info(f"Slug: {kwargs.get('slug', 'No slug')}")
        
        try:
            instance = self.get_object()
            logger.info(f"Found product: {instance.name} (ID: {instance.id})")
        except Exception as e:
            logger.error(f"Failed to get product: {e}")
            raise
        
        # Track activity using the new activity system
        user = request.user if request.user.is_authenticated else None
        session_key = request.session.session_key if not user else None
        
        # Ensure session key exists for anonymous users
        if not user and not session_key:
            request.session.save()
            session_key = request.session.session_key
        
        # Track the view activity
        UserClick.track_activity(
            product=instance,
            action='view',
            user=user,
            session_key=session_key,
            request=request
        )
        
        # Legacy view count update (keep for backward compatibility)
        Product.objects.filter(pk=instance.pk).update(view_count=F('view_count') + 1)
        
        serializer = self.get_serializer(instance)
        logger.info(f"Serialized data keys: {serializer.data.keys() if serializer.data else 'No data'}")
        logger.info("=== PRODUCT RETRIEVE REQUEST SUCCESS ===")
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
            # Track unfavorite activity
            UserClick.track_activity(
                product=product,
                action='unfavorite',
                user=request.user,
                request=request
            )
            # Legacy favorite count update (keep for backward compatibility)
            Product.objects.filter(pk=product.pk).update(
                favorite_count=F('favorite_count') - 1
            )
            return Response({'favorited': False})
        else:
            # Track favorite activity
            UserClick.track_activity(
                product=product,
                action='favorite',
                user=request.user,
                request=request
            )
            # Legacy favorite count update (keep for backward compatibility)
            Product.objects.filter(pk=product.pk).update(
                favorite_count=F('favorite_count') + 1
            )
            return Response({'favorited': True})

    @action(detail=True, methods=['post'])
    def click(self, request, slug=None):
        """Track product clicks with activity system"""
        product = self.get_object()
        
        # Track activity using the new activity system
        user = request.user if request.user.is_authenticated else None
        session_key = request.session.session_key if not user else None
        
        # Ensure session key exists for anonymous users
        if not user and not session_key:
            request.session.save()
            session_key = request.session.session_key
        
        # Track the click activity
        UserClick.track_activity(
            product=product,
            action='click',
            user=user,
            session_key=session_key,
            request=request
        )
        
        # Legacy click count update (keep for backward compatibility)
        Product.objects.filter(pk=product.pk).update(click_count=F('click_count') + 1)
        
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
        cart, created = Cart.objects.get_or_create(user=self.request.user)
        return Cart.objects.filter(user=self.request.user)

    def list(self, request, *args, **kwargs):
        """Get user's cart"""
        cart, created = Cart.objects.get_or_create(user=request.user)
        serializer = self.get_serializer(cart)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def add_item(self, request):
        """Add item to cart with comprehensive stock validation"""
        cart, created = Cart.objects.get_or_create(user=request.user)
        
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
            
            # Track cart addition activity
            UserClick.track_activity(
                product=product,
                action='cart_add',
                user=request.user,
                request=request
            )
            
            return Response({
                'success': True,
                'item': CartItemSerializer(cart_item).data,
                'message': 'Item added to cart successfully' if item_created else 'Cart item quantity updated',
                'was_created': item_created
            }, status=status.HTTP_201_CREATED if item_created else status.HTTP_200_OK)
        
        return Response({
            'error': 'VALIDATION_ERROR',
            'detail': 'Invalid data provided',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['patch'])
    def update_item(self, request):
        """Update cart item quantity with comprehensive stock validation"""
        cart = get_object_or_404(Cart, user=request.user)
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
        cart = get_object_or_404(Cart, user=request.user)
        item_id = request.data.get('item_id')
        
        if not item_id:
            return Response(
                {'detail': 'item_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        cart_item = get_object_or_404(CartItem, id=item_id, cart=cart)
        
        # Track cart removal activity before deleting
        UserClick.track_activity(
            product=cart_item.product,
            action='cart_remove',
            user=request.user,
            request=request
        )
        
        cart_item.delete()
        
        return Response({'detail': 'Item removed from cart'})

    @action(detail=False, methods=['delete'])
    def clear(self, request):
        """Clear all items from cart"""
        cart = get_object_or_404(Cart, user=request.user)
        cart.items.all().delete()
        return Response({'detail': 'Cart cleared'})


class OrderViewSet(viewsets.ModelViewSet):
    """
    ViewSet for orders
    """
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(buyer=self.request.user).prefetch_related('items')

    @action(detail=False, methods=['post'])
    def create_from_cart(self, request):
        """Create order from cart items with comprehensive stock validation"""
        cart = get_object_or_404(Cart, user=request.user)
        
        if not cart.items.exists():
            return Response(
                {'error': 'EMPTY_CART', 'detail': 'Cart is empty'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        shipping_address = request.data.get('shipping_address')
        if not shipping_address:
            return Response(
                {'error': 'MISSING_ADDRESS', 'detail': 'Shipping address is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Pre-purchase stock validation
        stock_errors = []
        unavailable_products = []
        
        with transaction.atomic():
            # First pass: Validate all items before processing any
            for cart_item in cart.items.select_related('product'):
                product = cart_item.product
                
                # Check if product is still active
                if not product.is_active:
                    unavailable_products.append({
                        'product_name': product.name,
                        'reason': 'Product is no longer available'
                    })
                    continue
                
                # Refresh stock from database to get latest value
                product.refresh_from_db()
                
                # Check stock availability
                if cart_item.quantity > product.stock_quantity:
                    stock_errors.append({
                        'product_id': str(product.id),
                        'product_name': product.name,
                        'requested_quantity': cart_item.quantity,
                        'available_stock': product.stock_quantity,
                        'error': 'INSUFFICIENT_STOCK'
                    })
                
                # Check if product is completely out of stock
                if product.stock_quantity <= 0:
                    stock_errors.append({
                        'product_id': str(product.id),
                        'product_name': product.name,
                        'requested_quantity': cart_item.quantity,
                        'available_stock': 0,
                        'error': 'OUT_OF_STOCK'
                    })
            
            # If there are any stock issues, return comprehensive error
            if stock_errors or unavailable_products:
                return Response(
                    {
                        'error': 'STOCK_VALIDATION_FAILED',
                        'detail': 'Some items in your cart are no longer available or have insufficient stock',
                        'stock_errors': stock_errors,
                        'unavailable_products': unavailable_products,
                        'action_required': 'Please update your cart quantities or remove unavailable items'
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Calculate totals - ensure all values are Decimal for proper calculation
            from decimal import Decimal
            
            subtotal = cart.total_amount
            shipping_cost = Decimal(str(request.data.get('shipping_cost', 0)))
            tax_amount = Decimal(str(request.data.get('tax_amount', 0)))
            discount_amount = Decimal(str(request.data.get('discount_amount', 0)))
            total_amount = subtotal + shipping_cost + tax_amount - discount_amount
            
            # Create order
            order = Order.objects.create(
                buyer=request.user,
                subtotal=subtotal,
                shipping_cost=shipping_cost,
                tax_amount=tax_amount,
                discount_amount=discount_amount,
                total_amount=total_amount,
                shipping_address=shipping_address,
                buyer_notes=request.data.get('buyer_notes', '')
            )
            
            successful_items = []
            failed_items = []
            
            # Second pass: Create order items and reduce stock
            for cart_item in cart.items.select_related('product'):
                product = cart_item.product
                
                try:
                    # Double-check stock one more time (race condition protection)
                    product.refresh_from_db()
                    if cart_item.quantity > product.stock_quantity:
                        failed_items.append({
                            'product_name': product.name,
                            'reason': f'Stock changed during checkout. Only {product.stock_quantity} available.'
                        })
                        continue
                    
                    # Create order item
                    order_item = OrderItem.objects.create(
                        order=order,
                        product=product,
                        seller=product.seller,
                        quantity=cart_item.quantity,
                        unit_price=product.price,
                        product_name=product.name,
                        product_description=product.description,
                        product_image=product.images.filter(is_primary=True).first().image.url if product.images.filter(is_primary=True).exists() else ''
                    )
                    
                    # Reduce stock atomically
                    updated_rows = Product.objects.filter(
                        id=product.id,
                        stock_quantity__gte=cart_item.quantity
                    ).update(
                        stock_quantity=F('stock_quantity') - cart_item.quantity
                    )
                    
                    if updated_rows == 0:
                        # Stock was reduced by another transaction
                        failed_items.append({
                            'product_name': product.name,
                            'reason': 'Stock was reserved by another customer during checkout'
                        })
                        order_item.delete()  # Remove the order item
                        continue
                    
                    successful_items.append({
                        'product_name': product.name,
                        'quantity': cart_item.quantity
                    })
                    
                    # Update metrics
                    if hasattr(product, 'metrics'):
                        ProductMetrics.objects.filter(product=product).update(
                            total_sales=F('total_sales') + cart_item.quantity,
                            total_revenue=F('total_revenue') + cart_item.total_price
                        )
                        
                except Exception as e:
                    logger.error(f"Error processing cart item {cart_item.id}: {str(e)}")
                    failed_items.append({
                        'product_name': product.name,
                        'reason': 'An error occurred while processing this item'
                    })
            
            # If no items could be processed, delete the order
            if not successful_items:
                order.delete()
                return Response(
                    {
                        'error': 'ORDER_PROCESSING_FAILED',
                        'detail': 'No items could be processed from your cart',
                        'failed_items': failed_items
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Clear cart (only successful items if there were failures)
            cart.items.all().delete()
            
            # Recalculate order totals if some items failed
            if failed_items:
                order.refresh_from_db()
                actual_subtotal = sum(item.total_price for item in order.items.all())
                order.subtotal = actual_subtotal
                order.total_amount = actual_subtotal + order.shipping_cost + order.tax_amount - order.discount_amount
                order.save()
            
            serializer = OrderSerializer(order)
            response_data = {
                'success': True,
                'order': serializer.data,
                'successful_items': successful_items,
                'message': 'Order created successfully'
            }
            
            if failed_items:
                response_data.update({
                    'partial_success': True,
                    'failed_items': failed_items,
                    'warning': 'Some items could not be processed due to stock issues'
                })
            
            return Response(response_data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['patch'])
    def update_status(self, request, pk=None):
        """Update order status (for sellers/admin)"""
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
        
        order.status = new_status
        order.save()
        
        return Response(OrderSerializer(order).data)


class ProductMetricsViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for product metrics - read-only for sellers
    """
    serializer_class = ProductMetricsSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ProductMetrics.objects.filter(product__seller=self.request.user)