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
import uuid
import os
import asyncio

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logger.warning("PIL/Pillow not available - image validation will be limited")

# Import transaction utilities
from utils.transaction_utils import (
    product_transaction, atomic_with_isolation, 
    rollback_safe_operation, log_transaction_performance
)

# Import S3 storage utilities
from utils.s3_storage import S3StorageError, get_s3_storage
from django.conf import settings

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
from .permissions import IsSellerOrReadOnly, IsOwnerOrReadOnly, IsSellerUser, IsAdminUser

# Set up logger
logger = logging.getLogger(__name__)

def validate_and_process_image(image_file, max_size_mb=10):
    """
    Validate image file extension, size, and generate random filename
    """
    # Allowed extensions
    ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
    MAX_SIZE = max_size_mb * 1024 * 1024  # Convert MB to bytes
    
    # Get file extension
    file_ext = os.path.splitext(image_file.name.lower())[1]
    
    # Validate extension
    if file_ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(f"Invalid file extension {file_ext}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")
    
    # Validate file size
    if image_file.size > MAX_SIZE:
        raise ValidationError(f"File size {image_file.size} bytes exceeds maximum {max_size_mb}MB")
    
    # Generate random filename
    random_name = f"{uuid.uuid4().hex}{file_ext}"
    
    # Additional validation: try to open as image (if PIL is available)
    if PIL_AVAILABLE:
        try:
            # Reset file pointer
            image_file.seek(0)
            # Verify it's a valid image
            with Image.open(image_file) as img:
                img.verify()
            # Reset file pointer again for upload
            image_file.seek(0)
        except Exception as e:
            raise ValidationError(f"Invalid image file: {str(e)}")
    else:
        # Basic validation without PIL - just check if file has content
        image_file.seek(0)
        content = image_file.read(1024)  # Read first 1KB
        if not content:
            raise ValidationError("Empty image file")
        image_file.seek(0)
    
    return {
        'file': image_file,
        'original_name': image_file.name,
        'random_name': random_name,
        'extension': file_ext,
        'size': image_file.size
    }


def start_background_tracking(tracking_func):
    """Helper function to start tracking in truly background thread."""
    try:
        import threading
        tracking_thread = threading.Thread(target=tracking_func, daemon=True)
        tracking_thread.start()
    except Exception as e:
        logger.error(f"Error starting background tracking: {str(e)}")

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
        ).select_related(
            'seller', 'category'
        ).prefetch_related(
            'images',
            'reviews__reviewer',
            'favorited_by'
        ).annotate(
            calculated_review_count=models.Count('reviews', filter=models.Q(reviews__is_active=True)),
            calculated_avg_rating=models.Avg('reviews__rating', filter=models.Q(reviews__is_active=True))
        )
        
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
    # Base queryset - minimal for list views
    queryset = Product.objects.filter(is_active=True).select_related(
        'seller', 'category'
    ).prefetch_related(
        'images'
    ).annotate(
        # Pre-calculate aggregated values to avoid repeated queries
        calculated_review_count=models.Count('reviews', filter=models.Q(reviews__is_active=True)),
        calculated_avg_rating=models.Avg('reviews__rating', filter=models.Q(reviews__is_active=True))
    )
    
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
        if self.action in ['create']:
            # Only sellers and admins can create products
            return [IsAuthenticated(), IsSellerUser()]
        elif self.action in ['update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSellerOrReadOnly()]
        elif self.action in ['my_products']:
            # Only sellers can view their products
            return [IsAuthenticated(), IsSellerUser()]
        return super().get_permissions()
    
    def get_queryset(self):
        """Override to add action-specific and user-specific optimizations"""
        queryset = super().get_queryset()

        # For detail views, prefetch reviews with reviewer info
        if self.action == 'retrieve':
            queryset = queryset.prefetch_related(
                'reviews__reviewer'
            )

        # If user is authenticated, prefetch their favorites for this queryset
        if hasattr(self.request, 'user') and self.request.user.is_authenticated:
            queryset = queryset.prefetch_related(
                models.Prefetch(
                    'favorited_by',
                    queryset=ProductFavorite.objects.filter(user=self.request.user),
                    to_attr='user_favorites'
                )
            )

        return queryset
    
    def create(self, request, *args, **kwargs):
        """Override create method with enhanced error handling for file uploads"""
        try:
            serializer = self.get_serializer(data=request.data)
            
            if serializer.is_valid():
                product = self.perform_create(serializer)
                headers = self.get_success_headers(serializer.data)
                
                # Add image information with presigned URLs to response
                response_data = serializer.data.copy()
                try:
                    # Get all product images with presigned URLs
                    product_images = product.images.order_by('order', 'id')
                    if product_images:
                        images_data = ProductImageSerializer(product_images, many=True).data
                        response_data['images'] = images_data
                        response_data['primary_image'] = next(
                            (img for img in images_data if img['is_primary']), 
                            images_data[0] if images_data else None
                        )
                        response_data['total_images'] = len(images_data)
                    else:
                        response_data['images'] = []
                        response_data['primary_image'] = None
                        response_data['total_images'] = 0
                except Exception as e:
                    logger.warning(f"Could not fetch product images for response: {str(e)}")
                    response_data['images'] = []
                    response_data['primary_image'] = None
                    response_data['total_images'] = 0
                
                return Response(response_data, status=status.HTTP_201_CREATED, headers=headers)
            else:
                logger.error(f"Product creation validation errors: {serializer.errors}")
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            logger.error(f"Unexpected error during product creation: {str(e)}")
            return Response({
                'detail': 'An error occurred while creating the product. Please try again.',
                'error': str(e) if settings.DEBUG else 'Internal server error'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def perform_create(self, serializer):
        """Create a new product with async metrics initialization and S3 image handling"""
        user = self.request.user
        
        # Create the product first
        product = serializer.save(seller=user)
        
        # Handle S3 image uploads after product creation (if S3 is enabled)
        if getattr(settings, 'USE_S3', False):
            uploaded_images = []
            
            # Debug: Log all available files
            logger.info(f"=== FILES DEBUG ===")
            logger.info(f"request.FILES keys: {list(self.request.FILES.keys())}")
            if settings.DEBUG:
                logger.info(f"request.data keys: {list(self.request.data.keys())}")
                for key, value in self.request.FILES.items():
                    logger.info(f"FILES[{key}]: {value} (type: {type(value).__name__})")
            
            # Get image files from request - try all possible field names
            image_files = self.request.FILES.getlist('images', [])  # Gallery images
            main_image = self.request.FILES.get('main_image')  # Main image
            uploaded_images_field = self.request.FILES.getlist('uploaded_images', [])  # Alternative field name
            
            # Also try to get all file-like objects from any field
            all_file_fields = []
            for key, file_obj in self.request.FILES.items():
                if hasattr(file_obj, 'read') and hasattr(file_obj, 'name'):
                    all_file_fields.append(('uploaded', file_obj))
                    logger.info(f"Found file in field '{key}': {file_obj.name}")
            
            # Debug: Log what we found
            logger.info(f"Found {len(image_files)} gallery images")
            logger.info(f"Found main_image: {main_image is not None}")
            logger.info(f"Found {len(uploaded_images_field)} uploaded_images")
            logger.info(f"Found {len(all_file_fields)} total file objects")
            
            # Combine all image sources
            all_images = []
            if main_image:
                all_images.append(('main', main_image))
            
            # Add gallery images
            for img in image_files:
                all_images.append(('gallery', img))
                
            # Add uploaded_images as gallery
            for img in uploaded_images_field:
                all_images.append(('gallery', img))
            
            # If no images found in traditional fields, use all file objects found
            if not all_images and all_file_fields:
                logger.info("No images found in traditional fields, using all file objects")
                all_images = all_file_fields
            
            # Upload to S3 if we have images
            logger.info(f"=== S3 UPLOAD PHASE ===")
            logger.info(f"Total images to process: {len(all_images)}")
            
            if all_images:
                try:
                    s3_storage = get_s3_storage()
                    
                    for i, (image_type, image_file) in enumerate(all_images):
                        try:
                            # Validate and process image (extension, size, random name)
                            logger.info(f"Processing image {i}: {image_file.name} ({image_file.size} bytes)")
                            validated_image = validate_and_process_image(image_file, max_size_mb=10)
                            logger.info(f"Image validated: {validated_image['random_name']} (was {validated_image['original_name']})")
                            
                            # Validate encoding metadata if provided
                            encoding_metadata = {}
                            try:
                                # Extract encoding metadata sent from frontend
                                encoding = self.request.data.get(f'image_{i}_encoding')
                                quality = self.request.data.get(f'image_{i}_quality')
                                original_size = self.request.data.get(f'image_{i}_original_size')
                                encoded_size = self.request.data.get(f'image_{i}_encoded_size')
                                compression_ratio = self.request.data.get(f'image_{i}_compression_ratio')
                                
                                if all([encoding, quality, original_size, encoded_size, compression_ratio]):
                                    # Validate encoding metadata
                                    encoding_validation = s3_storage._validate_encoding_metadata(
                                        encoding=encoding,
                                        quality=float(quality),
                                        original_size=int(original_size),
                                        encoded_size=int(encoded_size),
                                        compression_ratio=float(compression_ratio)
                                    )
                                    encoding_metadata = encoding_validation
                                    logger.info(f"Encoding metadata validated for image {i}: {encoding_metadata}")
                                else:
                                    logger.info(f"No encoding metadata provided for image {i}, proceeding with basic validation")
                                    
                            except (ValueError, TypeError, S3StorageError) as e:
                                logger.warning(f"Invalid encoding metadata for image {i}: {str(e)}")
                                # Continue with upload but log the issue
                            
                            # Set random filename
                            original_filename = image_file.name
                            image_file.name = validated_image['random_name']
                            
                            result = s3_storage.upload_product_image(
                                product_id=str(product.id),
                                image_file=image_file,
                                image_type=image_type
                            )
                            
                            # Create ProductImage record with S3 information
                            from .models import ProductImage
                            product_image = ProductImage.objects.create(
                                product=product,
                                s3_key=result['key'],
                                s3_bucket=s3_storage.bucket_name,
                                original_filename=original_filename,
                                file_size=result['size'],
                                content_type=validated_image.get('content_type', ''),
                                is_primary=(image_type == 'main' or i == 0),  # First image or main is primary
                                order=i + 1  # Order starts from 1, 2, 3, 4, 5, 6
                            )
                            
                            uploaded_images.append({
                                'id': product_image.id,
                                'type': image_type,
                                'url': result['url'],
                                'presigned_url': product_image.get_presigned_url(),
                                'key': result['key'],
                                'size': result['size'],
                                'filename': validated_image['random_name'],
                                'original_filename': original_filename,
                                'validated_extension': validated_image['extension'],
                                'validated_size': validated_image['size']
                            })
                            logger.info(f"Uploaded {image_type} image for product {product.id}: {result['key']} (DB record: {product_image.id})")
                        except ValidationError as e:
                            logger.error(f"Image validation failed for {image_file.name}: {str(e)}")
                            continue
                        except S3StorageError as e:
                            logger.error(f"Failed to upload {image_type} image for product {product.id}: {str(e)}")
                            continue
                        except Exception as e:
                            logger.error(f"Unexpected error processing image {image_file.name}: {str(e)}")
                            continue
                    
                    if uploaded_images:
                        logger.info(f"Successfully uploaded {len(uploaded_images)} images for product {product.id}")
                        # Store S3 info in product metadata if needed
                        # product.s3_images = uploaded_images  # If you have such a field
                        # product.save()
                        
                except Exception as e:
                    logger.error(f"S3 storage error during product creation for {product.id}: {str(e)}")
                    # Don't fail product creation if S3 upload fails
            else:
                logger.warning(f"No images found to upload for product {product.id}")
                logger.warning(f"This might indicate an issue with file detection or FormData processing")
        
        # Queue async metrics initialization for the new product
        try:
            from .async_tracking import AsyncTracker
            AsyncTracker.initialize()
            logger.info(f"Product created: {product.name} - metrics will be initialized asynchronously")
        except Exception as e:
            logger.error(f"Failed to initialize async metrics for product {product.id}: {e}")
            # Don't fail the product creation if async initialization fails
        
        return product

    def list(self, request, *args, **kwargs):
        """Override list method with truly async view tracking"""
        queryset = self.filter_queryset(self.get_queryset())
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response_data = serializer.data
            
            # Log AWS presigned URLs for product listing
            logger.info(f"=== PRODUCT LIST - AWS PRESIGNED URLS DEBUG ===")
            logger.info(f"Total products in page: {len(page)}")
            
            for i, product_data in enumerate(response_data['results'] if 'results' in response_data else response_data):
                logger.info(f"Product {i+1}: {product_data.get('name')} (ID: {product_data.get('id')})")
                primary_image = product_data.get('primary_image')
                if primary_image:
                    logger.info(f"  - Primary Image ID: {primary_image.get('id')}")
                    logger.info(f"  - S3 Key: {primary_image.get('s3_key')}")
                    logger.info(f"  - Presigned URL: {primary_image.get('presigned_url')}")
                    print(f"📋 LIST - AWS PRESIGNED URL for {product_data.get('name')}: {primary_image.get('presigned_url')}")
                else:
                    logger.info(f"  - No primary image found")
                    print(f"⚠️  LIST - No primary image for: {product_data.get('name')}")
            
            response = self.get_paginated_response(response_data)
            
            # Queue async tracking AFTER response is ready
            from .async_tracking import AsyncTracker
            start_background_tracking(lambda: AsyncTracker.queue_listing_view(page, request))
            
            return response

        serializer = self.get_serializer(queryset, many=True)
        response_data = serializer.data
        
        # Log AWS presigned URLs for non-paginated listing
        logger.info(f"=== PRODUCT LIST (NON-PAGINATED) - AWS PRESIGNED URLS DEBUG ===")
        logger.info(f"Total products: {len(response_data)}")
        
        for i, product_data in enumerate(response_data):
            logger.info(f"Product {i+1}: {product_data.get('name')} (ID: {product_data.get('id')})")
            primary_image = product_data.get('primary_image')
            if primary_image:
                logger.info(f"  - Primary Image ID: {primary_image.get('id')}")
                logger.info(f"  - S3 Key: {primary_image.get('s3_key')}")
                logger.info(f"  - Presigned URL: {primary_image.get('presigned_url')}")
                print(f"📋 LIST - AWS PRESIGNED URL for {product_data.get('name')}: {primary_image.get('presigned_url')}")
            else:
                logger.info(f"  - No primary image found")
                print(f"⚠️  LIST - No primary image for: {product_data.get('name')}")
        
        response = Response(response_data)
        
        # Queue async tracking AFTER response is ready  
        from .async_tracking import AsyncTracker
        products_list = list(queryset)
        start_background_tracking(lambda: AsyncTracker.queue_listing_view(products_list, request))
        
        return response

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        
        serializer = self.get_serializer(instance)
        response_data = serializer.data
        
        # Log AWS presigned URLs for debugging
        logger.info(f"=== PRODUCT RETRIEVE - AWS PRESIGNED URLS DEBUG ===")
        logger.info(f"Product: {instance.name} (ID: {instance.id}, Slug: {instance.slug})")
        
        if 'images' in response_data and response_data['images']:
            logger.info(f"Total images found: {len(response_data['images'])}")
            for i, image in enumerate(response_data['images']):
                logger.info(f"Image {i+1}:")
                logger.info(f"  - ID: {image.get('id')}")
                logger.info(f"  - Order: {image.get('order')}")
                logger.info(f"  - Is Primary: {image.get('is_primary')}")
                logger.info(f"  - S3 Key: {image.get('s3_key')}")
                logger.info(f"  - Original Filename: {image.get('original_filename')}")
                logger.info(f"  - Presigned URL: {image.get('presigned_url')}")
                logger.info(f"  - Image URL (fallback): {image.get('image_url')}")
                print(f"🖼️  AWS PRESIGNED URL {i+1}: {image.get('presigned_url')}")
        else:
            logger.info("No images found for this product")
            print(f"⚠️  No images found for product: {instance.name}")
        
        response = Response(response_data)
        
        # Queue async tracking AFTER response is ready
        from .async_tracking import AsyncTracker
        start_background_tracking(lambda: AsyncTracker.queue_product_view(instance, request))
        
        return response

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
            response = Response({'favorited': False})
            # Queue async tracking AFTER response is ready
            try:
                from .async_tracking import AsyncTracker
                import threading
                tracking_thread = threading.Thread(
                    target=lambda: AsyncTracker.queue_favorite_action(product, request.user, 'unfavorite', request),
                    daemon=True
                )
                tracking_thread.start()
            except Exception as e:
                logger.error(f"Error starting background tracking: {str(e)}")
            return response
        else:
            response = Response({'favorited': True})
            # Queue async tracking AFTER response is ready
            try:
                from .async_tracking import AsyncTracker
                import threading
                tracking_thread = threading.Thread(
                    target=lambda: AsyncTracker.queue_favorite_action(product, request.user, 'favorite', request),
                    daemon=True
                )
                tracking_thread.start()
            except Exception as e:
                logger.error(f"Error starting background tracking: {str(e)}")
            return response

    @action(detail=True, methods=['post'])
    def click(self, request, slug=None):
        """Track product clicks with truly async activity system"""
        product = self.get_object()
        
        response = Response({'clicked': True})
        
        # Queue async tracking AFTER response is ready
        try:
            from .async_tracking import AsyncTracker
            import threading
            tracking_thread = threading.Thread(
                target=lambda: AsyncTracker.queue_product_click(product, request),
                daemon=True
            )
            tracking_thread.start()
        except Exception as e:
            logger.error(f"Error starting background tracking: {str(e)}")
        
        return response

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
        # Include request in serializer context so nested ProductListSerializer
        # can compute user-specific fields like is_favorited
        serializer = ProductFavoriteSerializer(favorites, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def images(self, request, slug=None):
        """Get all S3 images for a product"""
        if not getattr(settings, 'USE_S3', False):
            return Response({
                'detail': 'S3 storage is not enabled',
                'images': []
            })
        
        product = self.get_object()
        
        try:
            s3_storage = get_s3_storage()
            images = s3_storage.get_product_images(str(product.id))
            
            return Response({
                'product_id': str(product.id),
                'product_name': product.name,
                'images': images,
                'total_images': len(images)
            })
            
        except S3StorageError as e:
            logger.error(f"Failed to get images for product {product.id}: {str(e)}")
            return Response({
                'detail': f'Failed to retrieve images: {str(e)}',
                'images': []
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def upload_image(self, request, slug=None):
        """Upload additional images to S3 for a product"""
        if not getattr(settings, 'USE_S3', False):
            return Response({
                'detail': 'S3 storage is not enabled'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        product = self.get_object()
        
        # Check if user owns the product
        if product.seller != request.user:
            return Response({
                'detail': 'You can only upload images to your own products'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get image file from request
        image_file = request.FILES.get('image')
        if not image_file:
            return Response({
                'detail': 'Image file is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get image type (default to gallery)
        image_type = request.data.get('image_type', 'gallery')
        if image_type not in ['main', 'gallery', 'thumbnail']:
            image_type = 'gallery'
        
        try:
            s3_storage = get_s3_storage()
            result = s3_storage.upload_product_image(
                product_id=str(product.id),
                image_file=image_file,
                image_type=image_type
            )
            
            logger.info(f"User {request.user.username} uploaded {image_type} image for product {product.id}")
            
            return Response({
                'success': True,
                'message': f'{image_type.title()} image uploaded successfully',
                'image': {
                    'url': result['url'],
                    'key': result['key'],
                    'size': result['size'],
                    'type': image_type,
                    'uploaded_at': result['uploaded_at']
                }
            }, status=status.HTTP_201_CREATED)
            
        except S3StorageError as e:
            logger.error(f"Failed to upload image for product {product.id}: {str(e)}")
            return Response({
                'detail': f'Failed to upload image: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['delete'], permission_classes=[IsAuthenticated])
    def delete_image(self, request, slug=None):
        """Delete a specific S3 image for a product"""
        if not getattr(settings, 'USE_S3', False):
            return Response({
                'detail': 'S3 storage is not enabled'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        product = self.get_object()
        
        # Check if user owns the product
        if product.seller != request.user:
            return Response({
                'detail': 'You can only delete images from your own products'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get image key from request
        image_key = request.data.get('image_key')
        if not image_key:
            return Response({
                'detail': 'image_key is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            s3_storage = get_s3_storage()
            success = s3_storage.delete_specific_product_image(
                product_id=str(product.id),
                image_key=image_key
            )
            
            if success:
                logger.info(f"User {request.user.username} deleted image {image_key} for product {product.id}")
                return Response({
                    'success': True,
                    'message': 'Image deleted successfully',
                    'deleted_key': image_key
                })
            else:
                return Response({
                    'detail': 'Failed to delete image'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
        except S3StorageError as e:
            logger.error(f"Failed to delete image {image_key} for product {product.id}: {str(e)}")
            return Response({
                'detail': f'Failed to delete image: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['delete'], permission_classes=[IsAuthenticated])
    def delete_all_images(self, request, slug=None):
        """Delete all S3 images for a product"""
        if not getattr(settings, 'USE_S3', False):
            return Response({
                'detail': 'S3 storage is not enabled'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        product = self.get_object()
        
        # Check if user owns the product
        if product.seller != request.user:
            return Response({
                'detail': 'You can only delete images from your own products'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            s3_storage = get_s3_storage()
            deleted_count = s3_storage.delete_product_images(str(product.id))
            
            logger.info(f"User {request.user.username} deleted {deleted_count} images for product {product.id}")
            
            return Response({
                'success': True,
                'message': f'Deleted {deleted_count} images successfully',
                'deleted_count': deleted_count
            })
            
        except S3StorageError as e:
            logger.error(f"Failed to delete images for product {product.id}: {str(e)}")
            return Response({
                'detail': f'Failed to delete images: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['get'])
    def main_image(self, request, slug=None):
        """Get the main image for a product with presigned URL"""
        product = self.get_object()
        
        # Get primary image from database (supports both S3 and traditional storage)
        primary_image = product.images.filter(is_primary=True).first()
        if not primary_image:
            primary_image = product.images.order_by('order').first()
        
        if primary_image:
            # Use the ProductImageSerializer to get presigned URL
            image_data = ProductImageSerializer(primary_image).data
            
            # Log the AWS presigned URL
            logger.info(f"=== MAIN IMAGE ENDPOINT - AWS PRESIGNED URL ===")
            logger.info(f"Product: {product.name} (ID: {product.id}, Slug: {product.slug})")
            logger.info(f"Main Image ID: {image_data['id']}")
            logger.info(f"S3 Key: {image_data['s3_key']}")
            logger.info(f"Presigned URL: {image_data['presigned_url']}")
            print(f"🖼️  MAIN IMAGE - AWS PRESIGNED URL for {product.name}: {image_data['presigned_url']}")
            
            return Response({
                'product_id': str(product.id),
                'product_name': product.name,
                'product_slug': product.slug,
                'main_image': {
                    'id': image_data['id'],
                    'presigned_url': image_data['presigned_url'],
                    'image_url': image_data['image_url'],
                    'alt_text': image_data['alt_text'],
                    'is_primary': image_data['is_primary'],
                    'order': image_data['order'],
                    's3_key': image_data['s3_key'],
                    'original_filename': image_data['original_filename']
                }
            })
        else:
            logger.info(f"=== MAIN IMAGE ENDPOINT - NO IMAGE FOUND ===")
            logger.info(f"Product: {product.name} (ID: {product.id}, Slug: {product.slug})")
            print(f"⚠️  MAIN IMAGE - No image found for product: {product.name}")
            
            return Response({
                'product_id': str(product.id),
                'product_name': product.name,
                'product_slug': product.slug,
                'main_image': None,
                'message': 'No images found for this product'
            })

    @action(detail=True, methods=['get'])
    def images_with_presigned_urls(self, request, slug=None):
        """Get all images for a product with presigned URLs"""
        product = self.get_object()
        
        # Get all product images ordered by order field
        images = product.images.order_by('order', 'id')
        
        if images:
            # Use the ProductImageSerializer to get presigned URLs for all images
            images_data = ProductImageSerializer(images, many=True).data
            
            return Response({
                'product_id': str(product.id),
                'product_name': product.name,
                'product_slug': product.slug,
                'total_images': len(images_data),
                'images': images_data,
                'primary_image': next((img for img in images_data if img['is_primary']), 
                                    images_data[0] if images_data else None)
            })
        else:
            return Response({
                'product_id': str(product.id),
                'product_name': product.name,
                'product_slug': product.slug,
                'total_images': 0,
                'images': [],
                'primary_image': None,
                'message': 'No images found for this product'
            })


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


def send_cart_update_notification(user_id, action, product_id=None, message=None, quantity_change=None):
    """Fire-and-forget async cart update notification via WebSocket"""
    def async_notification():
        try:
            from activity.consumer import ActivityConsumer
            from marketplace.models import Cart, CartItem
            
            # Calculate current cart count
            user_cart = Cart.objects.filter(user_id=user_id).first()
            cart_count = 0
            if user_cart:
                cart_count = sum(item.quantity for item in CartItem.objects.filter(cart=user_cart))
            
            # Send WebSocket notification - fire and forget
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(
                ActivityConsumer.notify_cart_update(
                    user_id=user_id,
                    action=action,
                    product_id=product_id,
                    cart_count=cart_count,
                    message=message,
                    quantity_change=quantity_change
                )
            )
            loop.close()
        except Exception:
            # Silent failure - if WebSocket notification fails, we don't care
            pass
    
    # Fire and forget in daemon thread
    import threading
    threading.Thread(target=async_notification, daemon=True).start()


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
        """Add item to cart with comprehensive stock validation and row-level locking"""
        cart = Cart.get_or_create_cart(user=request.user)

        serializer = CartItemSerializer(data=request.data)
        if serializer.is_valid():
            product_id = serializer.validated_data['product_id']
            quantity = serializer.validated_data['quantity']

            try:
                with transaction.atomic():
                    # Lock product row to avoid race conditions (overselling)
                    product = Product.objects.select_for_update().get(id=product_id, is_active=True)

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

                    # Get or create this user's cart item and lock it
                    cart_item, item_created = CartItem.objects.select_for_update().get_or_create(
                        cart=cart, product=product,
                        defaults={'quantity': 0}
                    )

                    # Compute new quantity and validate against total stock only (no cross-cart reservation)
                    new_quantity = cart_item.quantity + quantity
                    if new_quantity > product.stock_quantity:
                        return Response(
                            {
                                'error': 'INSUFFICIENT_STOCK',
                                'detail': f'Only {product.stock_quantity} items available in stock',
                                'available_stock': product.stock_quantity,
                                'requested_quantity': new_quantity,
                                'current_in_cart': cart_item.quantity
                            },
                            status=status.HTTP_400_BAD_REQUEST
                        )

                    cart_item.quantity = new_quantity
                    cart_item.save()
            except Product.DoesNotExist:
                return Response(
                    {'error': 'PRODUCT_NOT_FOUND', 'detail': 'Product not found or not available'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Store response data first
            response_data = {
                'success': True,
                'item': CartItemSerializer(cart_item).data,
                'message': 'Item added to cart successfully' if item_created else 'Cart item quantity updated',
                'was_created': item_created
            }
            
            # Queue async tracking AFTER response is ready
            try:
                from .async_tracking import AsyncTracker
                import threading
                tracking_thread = threading.Thread(
                    target=lambda: AsyncTracker.queue_cart_action(product, request.user, 'cart_add', quantity, request),
                    daemon=True
                )
                tracking_thread.start()
            except Exception as e:
                logger.error(f"Error starting background tracking: {str(e)}")
            
            # Send WebSocket cart update notification
            send_cart_update_notification(
                user_id=request.user.id,
                action='add_item',
                product_id=product.id,
                message=f'Added {quantity} items to cart'
            )
            
            return Response(response_data, status=status.HTTP_201_CREATED if item_created else status.HTTP_200_OK)
        
        error_response = {
            'error': 'VALIDATION_ERROR',
            'detail': 'Invalid data provided',
            'errors': serializer.errors
        }
        
        return Response(error_response, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['patch'])
    def update_item(self, request):
        """Update cart item quantity with comprehensive stock validation and row-level locking"""
        cart = Cart.get_or_create_cart(user=request.user)
        
                
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
            product_id = cart_item.product.id
            removed_qty = cart_item.quantity
            cart_item.delete()
            
            # Send WebSocket cart update notification for removal, include removed quantity
            send_cart_update_notification(
                user_id=request.user.id,
                action='remove_item',
                product_id=product_id,
                message='Item removed from cart',
                quantity_change=-int(removed_qty)
            )
            
            return Response({'detail': 'Item removed from cart'})
        
        # Enhanced stock validation inside a transaction to avoid race conditions
        with transaction.atomic():
            product = Product.objects.select_for_update().get(id=cart_item.product.id)
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

            previous_quantity = cart_item.quantity
            cart_item.quantity = quantity
            cart_item.save()
        
        # Send WebSocket cart update notification for quantity update
        send_cart_update_notification(
            user_id=request.user.id,
            action='update_item',
            product_id=product.id,
            message=f'Updated cart item quantity to {quantity}',
            quantity_change=int(quantity) - int(previous_quantity)
        )
        
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
        
        # Store cart info before deletion
        product = cart_item.product
        quantity = cart_item.quantity
        
        cart_item.delete()
        
        response = Response({'detail': 'Item removed from cart'})
        
        # Queue async tracking AFTER response is ready
        try:
            from .async_tracking import AsyncTracker
            import threading
            tracking_thread = threading.Thread(
                target=lambda: AsyncTracker.queue_cart_action(product, request.user, 'cart_remove', quantity, request),
                daemon=True
            )
            tracking_thread.start()
        except Exception as e:
            logger.error(f"Error starting background tracking: {str(e)}")
        
        # Send WebSocket cart update notification for item removal
        send_cart_update_notification(
            user_id=request.user.id,
            action='remove_item',
            product_id=product.id,
            message=f'Removed {quantity} items from cart',
            quantity_change=-int(quantity)
        )
        
        return response

    @action(detail=False, methods=['delete'])
    def clear(self, request):
        """Clear all items from cart"""
        cart = Cart.get_or_create_cart(user=request.user)
        
                
        cart.items.all().delete()
        
        # Send WebSocket cart update notification for cart clear
        send_cart_update_notification(
            user_id=request.user.id,
            action='clear_cart',
            message='Cart cleared'
        )
        
        return Response({'detail': 'Cart cleared'})
    
    @action(detail=False, methods=['patch'])
    def update_item_status(self, request):
        """Update cart item status"""
        cart = Cart.get_or_create_cart(user=request.user)
        
        
        item_id = request.data.get('item_id')
        new_status = request.data.get('status')
        
        if not item_id:
            return Response(
                {'error': 'MISSING_PARAMETERS', 'detail': 'item_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            cart_item = CartItem.objects.get(id=item_id, cart=cart)
            
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
            
            return Response(response_data)
            
        except CartItem.DoesNotExist:
            return Response(
                {'error': 'ITEM_NOT_FOUND', 'detail': 'Item not found in cart'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': 'INTERNAL_ERROR', 'detail': 'An unexpected error occurred'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def validate_stock(self, request):
        """Validate stock for all cart items"""
        cart = Cart.get_or_create_cart(user=request.user)
        
        validation_results = []
        all_valid = True
        
        for item in cart.items.all():
            
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
            
            # Check stock availability
            if item.product.stock_quantity < item.quantity:
                item_result['is_valid'] = False
                item_result['issues'].append(f'Insufficient stock. Available: {item.product.stock_quantity}')
                all_valid = False
            
            # Check if stock is zero
            if item.product.stock_quantity <= 0:
                item_result['is_valid'] = False
                item_result['issues'].append('Out of stock')
                all_valid = False
            
            validation_results.append(item_result)
        
        response_data = {
            'cart_valid': all_valid,
            'total_items': len(validation_results),
            'valid_items': sum(1 for r in validation_results if r['is_valid']),
            'invalid_items': sum(1 for r in validation_results if not r['is_valid']),
            'items': validation_results
        }
        
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

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated, IsSellerUser])
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
    permission_classes = [IsAuthenticated, IsSellerUser]

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


class UserProfileViewSet(viewsets.ViewSet):
    """
    ViewSet for user profile operations including S3 profile pictures
    """
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def profile_picture(self, request):
        """Get current user's profile picture from S3"""
        if not getattr(settings, 'USE_S3', False):
            return Response({
                'detail': 'S3 storage is not enabled',
                'profile_picture': None
            })
        
        try:
            s3_storage = get_s3_storage()
            profile_pic = s3_storage.get_profile_picture(str(request.user.id))
            
            return Response({
                'user_id': str(request.user.id),
                'username': request.user.username,
                'profile_picture': profile_pic
            })
            
        except S3StorageError as e:
            logger.error(f"Failed to get profile picture for user {request.user.id}: {str(e)}")
            return Response({
                'detail': f'Failed to retrieve profile picture: {str(e)}',
                'profile_picture': None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'])
    def upload_profile_picture(self, request):
        """Upload or update user's profile picture to S3"""
        if not getattr(settings, 'USE_S3', False):
            return Response({
                'detail': 'S3 storage is not enabled'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get image file from request
        image_file = request.FILES.get('profile_picture') or request.FILES.get('image')
        if not image_file:
            return Response({
                'detail': 'Profile picture file is required (use "profile_picture" or "image" field)'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate image file
        max_size = 5 * 1024 * 1024  # 5MB
        if image_file.size > max_size:
            return Response({
                'detail': f'Image file too large. Maximum size is {max_size // (1024*1024)}MB'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check file type
        allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp']
        if hasattr(image_file, 'content_type') and image_file.content_type not in allowed_types:
            return Response({
                'detail': f'Invalid file type. Allowed types: {", ".join(allowed_types)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            s3_storage = get_s3_storage()
            result = s3_storage.upload_profile_picture(
                user_id=str(request.user.id),
                image_file=image_file,
                replace_existing=True
            )
            
            logger.info(f"User {request.user.username} uploaded profile picture")
            
            return Response({
                'success': True,
                'message': 'Profile picture uploaded successfully',
                'profile_picture': {
                    'url': result['url'],
                    'key': result['key'],
                    'size': result['size'],
                    'uploaded_at': result['uploaded_at']
                }
            }, status=status.HTTP_201_CREATED)
            
        except S3StorageError as e:
            logger.error(f"Failed to upload profile picture for user {request.user.id}: {str(e)}")
            return Response({
                'detail': f'Failed to upload profile picture: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['delete'])
    def delete_profile_picture(self, request):
        """Delete user's profile picture from S3"""
        if not getattr(settings, 'USE_S3', False):
            return Response({
                'detail': 'S3 storage is not enabled'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            s3_storage = get_s3_storage()
            success = s3_storage.delete_profile_picture(str(request.user.id))
            
            if success:
                logger.info(f"User {request.user.username} deleted profile picture")
                return Response({
                    'success': True,
                    'message': 'Profile picture deleted successfully'
                })
            else:
                return Response({
                    'detail': 'No profile picture found to delete'
                }, status=status.HTTP_404_NOT_FOUND)
                
        except S3StorageError as e:
            logger.error(f"Failed to delete profile picture for user {request.user.id}: {str(e)}")
            return Response({
                'detail': f'Failed to delete profile picture: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['patch'])
    def update_profile_picture(self, request):
        """Update user's profile picture (alias for upload_profile_picture)"""
        return self.upload_profile_picture(request)

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from django.contrib.auth import get_user_model

User = get_user_model()


@api_view(['GET'])
@permission_classes([AllowAny])
def seller_profile(request, seller_id):
    """
    Get seller profile with their products and reviews.
    Public endpoint - accessible to everyone.
    """
    try:
        # Get the seller user
        seller = get_object_or_404(User, id=seller_id)
        
        # Check if user is actually a seller
        if seller.role not in ['seller', 'admin']:
            return Response({
                'error': 'User is not a seller'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get seller's products
        products = Product.objects.filter(
            seller=seller,
            is_active=True
        ).select_related('category').prefetch_related('images', 'reviews')
        
        # Get seller's reviews (from products they sold)
        reviews = ProductReview.objects.filter(
            product__seller=seller,
            is_active=True
        ).select_related('reviewer', 'product').order_by('-created_at')
        
        # Calculate seller stats
        total_products = products.count()
        total_reviews = reviews.count()
        
        # Calculate average rating
        if total_reviews > 0:
            average_rating = reviews.aggregate(models.Avg('rating'))['rating__avg']
        else:
            average_rating = 0
        
        # Calculate total sales (completed orders)
        total_sales = OrderItem.objects.filter(
            product__seller=seller,
            order__status='delivered'
        ).aggregate(total=Sum('quantity'))['total'] or 0
        
        # Serialize products
        product_serializer = ProductListSerializer(products, many=True, context={'request': request})
        
        # Serialize reviews
        review_serializer = ProductReviewSerializer(reviews[:20], many=True)  # Limit to 20 recent reviews
        
        # Build seller profile response
        return Response({
            'seller': {
                'id': seller.id,
                'username': seller.username,
                'first_name': seller.first_name,
                'last_name': seller.last_name,
                'email': seller.email,
                'role': seller.role,
                'date_joined': seller.date_joined,
            },
            'stats': {
                'total_products': total_products,
                'total_reviews': total_reviews,
                'average_rating': round(average_rating, 2) if average_rating else 0,
                'total_sales': total_sales,
            },
            'products': product_serializer.data,
            'reviews': review_serializer.data,
        }, status=status.HTTP_200_OK)
        
    except User.DoesNotExist:
        return Response({
            'error': 'Seller not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error fetching seller profile: {str(e)}")
        return Response({
            'error': 'Failed to fetch seller profile'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
