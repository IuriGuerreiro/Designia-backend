from rest_framework import serializers
from django.contrib.auth import get_user_model
import logging
import json
from .models import (
    Category, Product, ProductImage, ProductReview, ProductFavorite,
    Order, OrderItem, Cart, CartItem, ProductMetrics
)

User = get_user_model()

# Set up logger
logger = logging.getLogger(__name__)

class FlexibleJSONField(serializers.Field):
    """Custom field that can handle both JSON strings and lists for FormData"""
    
    def to_internal_value(self, data):
        if isinstance(data, str):
            try:
                return json.loads(data) if data.strip() else []
            except (json.JSONDecodeError, ValueError):
                return []
        elif isinstance(data, list):
            return data
        elif data is None:
            return []
        else:
            return []
    
    def to_representation(self, value):
        return value if value is not None else []

class UserSerializer(serializers.ModelSerializer):
    """Basic user serializer for seller information"""
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'avatar']
        read_only_fields = ['id']


class CategorySerializer(serializers.ModelSerializer):
    """Category serializer with subcategory support"""
    subcategories = serializers.SerializerMethodField()
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'description', 'parent', 'subcategories', 
                 'product_count', 'is_active', 'created_at']
        read_only_fields = ['id', 'slug', 'created_at', 'subcategories', 'product_count']

    def get_subcategories(self, obj):
        if obj.subcategories.exists():
            return CategorySerializer(obj.subcategories.filter(is_active=True), many=True).data
        return []

    def get_product_count(self, obj):
        return obj.products.filter(is_active=True).count()


class ProductImageSerializer(serializers.ModelSerializer):
    """Product image serializer"""
    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'alt_text', 'is_primary', 'order']
        read_only_fields = ['id']


class ProductReviewSerializer(serializers.ModelSerializer):
    """Product review serializer"""
    reviewer = UserSerializer(read_only=True)
    reviewer_name = serializers.CharField(source='reviewer.username', read_only=True)

    class Meta:
        model = ProductReview
        fields = ['id', 'reviewer', 'reviewer_name', 'rating', 'title', 'comment',
                 'is_verified_purchase', 'created_at', 'updated_at']
        read_only_fields = ['id', 'reviewer', 'reviewer_name', 'is_verified_purchase', 
                           'created_at', 'updated_at']

    def validate_rating(self, value):
        if not 1 <= value <= 5:
            raise serializers.ValidationError("Rating must be between 1 and 5")
        return value


class ProductListSerializer(serializers.ModelSerializer):
    """Minimal product serializer for lists"""
    seller = UserSerializer(read_only=True)
    category = CategorySerializer(read_only=True)
    primary_image = serializers.SerializerMethodField()
    is_favorited = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ['id', 'name', 'slug', 'short_description', 'seller', 'category',
                 'price', 'original_price', 'condition', 'brand', 'primary_image',
                 'is_featured', 'is_digital', 'average_rating', 'review_count',
                 'is_in_stock', 'is_on_sale', 'discount_percentage', 'is_favorited',
                 'created_at', 'view_count', 'favorite_count']
        read_only_fields = ['id', 'slug', 'seller', 'average_rating', 'review_count',
                           'is_in_stock', 'is_on_sale', 'discount_percentage',
                           'created_at', 'view_count', 'favorite_count']

    def get_primary_image(self, obj):
        primary_image = obj.images.filter(is_primary=True).first()
        if primary_image:
            return ProductImageSerializer(primary_image).data
        # Return first image if no primary image is set
        first_image = obj.images.first()
        if first_image:
            return ProductImageSerializer(first_image).data
        return None

    def get_is_favorited(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return ProductFavorite.objects.filter(user=request.user, product=obj).exists()
        return False


class ProductDetailSerializer(serializers.ModelSerializer):
    """Detailed product serializer"""
    seller = UserSerializer(read_only=True)
    category = CategorySerializer(read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    reviews = ProductReviewSerializer(many=True, read_only=True)
    is_favorited = serializers.SerializerMethodField()
    seller_product_count = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ['id', 'name', 'slug', 'description', 'short_description', 'seller',
                 'category', 'price', 'original_price', 'stock_quantity', 'condition',
                 'brand', 'model', 'weight', 'dimensions_length', 'dimensions_width',
                 'dimensions_height', 'colors', 'materials', 'tags', 'is_active',
                 'is_featured', 'is_digital', 'images', 'reviews', 'average_rating',
                 'review_count', 'is_in_stock', 'is_on_sale', 'discount_percentage',
                 'is_favorited', 'seller_product_count', 'created_at', 'updated_at',
                 'view_count', 'click_count', 'favorite_count']
        read_only_fields = ['id', 'slug', 'seller', 'average_rating', 'review_count',
                           'is_in_stock', 'is_on_sale', 'discount_percentage',
                           'seller_product_count', 'created_at', 'updated_at',
                           'view_count', 'click_count', 'favorite_count']

    def get_is_favorited(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return ProductFavorite.objects.filter(user=request.user, product=obj).exists()
        return False

    def get_seller_product_count(self, obj):
        return obj.seller.products.filter(is_active=True).count()


class ProductCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating products"""
    images = ProductImageSerializer(many=True, read_only=True)
    uploaded_images = serializers.ListField(
        child=serializers.ImageField(), write_only=True, required=False
    )
    # Use custom field for JSON data that can come as strings from FormData
    colors = FlexibleJSONField(required=False)
    tags = FlexibleJSONField(required=False)

    class Meta:
        model = Product
        fields = ['id', 'name', 'description', 'short_description', 'category',
                 'price', 'original_price', 'stock_quantity', 'condition', 'brand',
                 'model', 'weight', 'dimensions_length', 'dimensions_width',
                 'dimensions_height', 'colors', 'materials', 'tags', 'is_featured',
                 'is_digital', 'images', 'uploaded_images']
        read_only_fields = ['id', 'images']

    def to_internal_value(self, data):
        """Debug incoming data before validation and handle FormData parsing"""
        logger.info("=== SERIALIZER TO_INTERNAL_VALUE DEBUG START ===")
        logger.info(f"Raw data type: {type(data)}")
        logger.info(f"Raw data keys: {list(data.keys()) if hasattr(data, 'keys') else 'No keys method'}")
        
        # Create a mutable copy for processing
        processed_data = data.copy() if hasattr(data, 'copy') else dict(data)
        
        # Log each field safely
        for key, value in processed_data.items():
            if hasattr(value, 'read'):  # File-like object
                logger.info(f"Field {key}: <File: {getattr(value, 'name', 'unknown')}>")
            else:
                logger.info(f"Field {key}: {value} (type: {type(value).__name__})")
        
        # Handle string boolean fields from FormData
        boolean_fields = ['is_featured', 'is_digital']
        for field in boolean_fields:
            if field in processed_data:
                value = processed_data[field]
                if isinstance(value, str):
                    processed_data[field] = value.lower() in ('true', '1', 'yes', 'on')
                    logger.info(f"Converted {field} from '{value}' to {processed_data[field]}")
        
        # JSON fields (colors, tags) are now handled by FlexibleJSONField automatically
        # No need to manually parse them here
        
        # Handle numeric fields that might come as strings from FormData
        numeric_fields = ['stock_quantity']
        for field in numeric_fields:
            if field in processed_data and isinstance(processed_data[field], str):
                try:
                    processed_data[field] = int(processed_data[field])
                    logger.info(f"Converted {field} to integer: {processed_data[field]}")
                except (ValueError, TypeError) as e:
                    logger.error(f"Failed to convert {field} to integer: {e}")
        
        # Handle decimal fields that might come as strings from FormData
        decimal_fields = ['price', 'original_price', 'weight', 'dimensions_length', 'dimensions_width', 'dimensions_height']
        for field in decimal_fields:
            if field in processed_data and isinstance(processed_data[field], str):
                if processed_data[field].strip():  # Only process non-empty strings
                    try:
                        from decimal import Decimal
                        processed_data[field] = Decimal(processed_data[field])
                        logger.info(f"Converted {field} to decimal: {processed_data[field]}")
                    except (ValueError, TypeError) as e:
                        logger.error(f"Failed to convert {field} to decimal: {e}")
                else:
                    # Remove empty string values for optional decimal fields
                    if field in ['original_price', 'weight', 'dimensions_length', 'dimensions_width', 'dimensions_height']:
                        processed_data[field] = None
                        logger.info(f"Set empty {field} to None")
        
        # Handle empty category field - remove it so validation will catch it
        if 'category' in processed_data and isinstance(processed_data['category'], str):
            if not processed_data['category'].strip():
                logger.warning("Category field is empty, removing from data")
                del processed_data['category']  # Let Django validation handle the missing required field
        
        try:
            result = super().to_internal_value(processed_data)
            logger.info("=== SERIALIZER TO_INTERNAL_VALUE DEBUG - SUCCESS ===")
            return result
        except Exception as e:
            logger.error(f"to_internal_value failed: {str(e)}")
            logger.error(f"Error type: {type(e).__name__}")
            if hasattr(e, 'detail'):
                logger.error(f"Error detail: {e.detail}")
            logger.error("=== SERIALIZER TO_INTERNAL_VALUE DEBUG - FAILED ===")
            raise

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Price must be greater than 0")
        return value

    def validate_original_price(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Original price must be greater than 0")
        return value
    
    def validate_category(self, value):
        if not value:
            raise serializers.ValidationError("Category is required")
        return value

    def validate(self, data):
        logger.info("=== SERIALIZER VALIDATION DEBUG START ===")
        logger.info(f"Data keys: {list(data.keys())}")
        
        # Log data safely (excluding files)
        safe_data = {}
        for key, value in data.items():
            if hasattr(value, 'read'):  # File-like object
                safe_data[key] = f"<File: {getattr(value, 'name', 'unknown')}>"
            else:
                safe_data[key] = value
        logger.info(f"Validation data (safe): {safe_data}")
        
        # Validate that original price is higher than current price if both are set
        price = data.get('price')
        original_price = data.get('original_price')
        
        logger.info(f"Price validation - price: {price}, original_price: {original_price}")
        
        if original_price and price and original_price <= price:
            error_msg = "Original price must be higher than current price"
            logger.error(f"Price validation failed: {error_msg}")
            logger.error("=== SERIALIZER VALIDATION DEBUG - FAILED ===")
            raise serializers.ValidationError({
                "original_price": error_msg
            })
        
        logger.info("=== SERIALIZER VALIDATION DEBUG - SUCCESS ===")
        return data

    def create(self, validated_data):
        logger.info("=== SERIALIZER CREATE DEBUG START ===")
        logger.info(f"Validated data keys: {list(validated_data.keys())}")
        
        # Debug validated data safely
        safe_data = {}
        for key, value in validated_data.items():
            if hasattr(value, 'read'):  # File-like object
                safe_data[key] = f"<File: {getattr(value, 'name', 'unknown')}>"
            else:
                safe_data[key] = value
        logger.info(f"Validated data (safe): {safe_data}")
        
        uploaded_images = validated_data.pop('uploaded_images', [])
        logger.info(f"Uploaded images count: {len(uploaded_images)}")
        
        # Set seller to current user
        user = self.context['request'].user
        validated_data['seller'] = user
        logger.info(f"Setting seller to: {user.email} (ID: {user.id})")
        
        try:
            logger.info("Creating product object...")
            product = Product.objects.create(**validated_data)
            logger.info(f"Product created with ID: {product.id}, slug: {product.slug}")
            
            # Handle image uploads
            logger.info(f"Processing {len(uploaded_images)} images...")
            for i, image in enumerate(uploaded_images):
                logger.info(f"Creating ProductImage {i}: {image.name}")
                ProductImage.objects.create(
                    product=product,
                    image=image,
                    is_primary=(i == 0),  # First image is primary
                    order=i
                )
            
            logger.info("=== SERIALIZER CREATE DEBUG - SUCCESS ===")
            return product
            
        except Exception as e:
            logger.error(f"Error in serializer create: {str(e)}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error("=== SERIALIZER CREATE DEBUG - FAILED ===")
            raise

    def update(self, instance, validated_data):
        uploaded_images = validated_data.pop('uploaded_images', [])
        
        # Update product fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Handle new image uploads
        if uploaded_images:
            current_image_count = instance.images.count()
            for i, image in enumerate(uploaded_images):
                ProductImage.objects.create(
                    product=instance,
                    image=image,
                    is_primary=(current_image_count == 0 and i == 0),
                    order=current_image_count + i
                )
        
        return instance


class ProductFavoriteSerializer(serializers.ModelSerializer):
    """Product favorite serializer"""
    product = ProductListSerializer(read_only=True)

    class Meta:
        model = ProductFavorite
        fields = ['id', 'product', 'created_at']
        read_only_fields = ['id', 'created_at']


class CartItemSerializer(serializers.ModelSerializer):
    """Cart item serializer"""
    product = ProductListSerializer(read_only=True)
    product_id = serializers.UUIDField(write_only=True)
    total_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = CartItem
        fields = ['id', 'product', 'product_id', 'quantity', 'total_price', 'added_at']
        read_only_fields = ['id', 'total_price', 'added_at']

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than 0")
        return value

    def validate_product_id(self, value):
        try:
            product = Product.objects.get(id=value, is_active=True)
        except Product.DoesNotExist:
            raise serializers.ValidationError("Product not found or not available")
        return value

    def validate(self, data):
        product_id = data.get('product_id')
        quantity = data.get('quantity', 1)
        
        if product_id:
            try:
                product = Product.objects.get(id=product_id, is_active=True)
                if quantity > product.stock_quantity:
                    raise serializers.ValidationError({
                        "quantity": f"Only {product.stock_quantity} items available in stock"
                    })
            except Product.DoesNotExist:
                pass  # Already handled in validate_product_id
        
        return data


class CartSerializer(serializers.ModelSerializer):
    """Cart serializer"""
    items = CartItemSerializer(many=True, read_only=True)
    total_items = serializers.IntegerField(read_only=True)
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Cart
        fields = ['id', 'items', 'total_items', 'total_amount', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class OrderItemSerializer(serializers.ModelSerializer):
    """Order item serializer"""
    class Meta:
        model = OrderItem
        fields = ['id', 'product', 'seller', 'quantity', 'unit_price', 'total_price',
                 'product_name', 'product_description', 'product_image']
        read_only_fields = ['id', 'total_price']


class OrderSerializer(serializers.ModelSerializer):
    """Order serializer"""
    items = OrderItemSerializer(many=True, read_only=True)
    buyer = UserSerializer(read_only=True)

    class Meta:
        model = Order
        fields = ['id', 'buyer', 'status', 'payment_status', 'subtotal', 'shipping_cost',
                 'tax_amount', 'discount_amount', 'total_amount', 'shipping_address',
                 'tracking_number', 'shipping_carrier', 'items', 'buyer_notes',
                 'created_at', 'updated_at', 'shipped_at', 'delivered_at']
        read_only_fields = ['id', 'buyer', 'created_at', 'updated_at']

    def validate_shipping_address(self, value):
        required_fields = ['street', 'city', 'state', 'postal_code', 'country']
        for field in required_fields:
            if field not in value:
                raise serializers.ValidationError(f"Shipping address must include {field}")
        return value


class ProductMetricsSerializer(serializers.ModelSerializer):
    """Product metrics serializer"""
    class Meta:
        model = ProductMetrics
        fields = ['total_views', 'total_clicks', 'total_favorites', 'total_cart_additions',
                 'total_sales', 'total_revenue', 'view_to_click_rate', 'click_to_cart_rate',
                 'cart_to_purchase_rate', 'last_updated']
        read_only_fields = ['total_views', 'total_clicks', 'total_favorites', 
                           'total_cart_additions', 'total_sales', 'total_revenue',
                           'view_to_click_rate', 'click_to_cart_rate', 
                           'cart_to_purchase_rate', 'last_updated']