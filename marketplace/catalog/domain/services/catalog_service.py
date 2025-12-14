"""
CatalogService - Product CRUD & Search

Handles product browsing, CRUD operations, and basic search functionality.
Integrates with storage abstraction for image uploads.

Story 2.2: CatalogService - Product CRUD & Search
"""

import logging
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Count, OuterRef, Q, Subquery

# Phase 3: Observability
from authentication.infra.observability.tracing import tracer
from infrastructure.container import container
from infrastructure.storage.interface import StorageException
from marketplace.catalog.domain.models.catalog import Product, ProductImage
from marketplace.catalog.domain.models.category import Category
from marketplace.catalog.domain.models.interaction import ProductReview
from marketplace.catalog.domain.services.base import BaseService, ErrorCodes, ServiceResult, service_err, service_ok
from utils.rbac import is_seller


User = get_user_model()
logger = logging.getLogger(__name__)


class CatalogService(BaseService):
    """
    Service for managing product catalog operations.

    Responsibilities:
    - List products with filtering and pagination
    - Get product details
    - Create products (seller only)
    - Update products (owner only)
    - Delete products (owner only)
    - Basic product search
    - Handle product image uploads via storage abstraction

    All operations validate permissions and return ServiceResult.
    """

    def __init__(self, storage=None):
        """
        Initialize CatalogService.

        Args:
            storage: Storage abstraction (injected via DI container)
        """
        super().__init__()
        self.storage = storage or container.storage()

    @BaseService.log_performance
    def list_products(
        self,
        filters: Optional[Dict[str, Any]] = None,
        page: int = 1,
        page_size: int = 20,
        ordering: str = "-created_at",
    ) -> ServiceResult[Dict[str, Any]]:
        """
        List products with filtering and pagination.

        Args:
            filters: Optional filters (category, seller, is_active, etc.)
            page: Page number (1-indexed)
            page_size: Items per page
            ordering: Sort order (default: newest first)

        Returns:
            ServiceResult with paginated product list

        Example:
            >>> result = catalog_service.list_products(
            ...     filters={"category": "electronics", "is_active": True},
            ...     page=1,
            ...     page_size=20
            ... )
            >>> if result.ok:
            ...     products = result.value["results"]
            ...     total = result.value["count"]
        """
        with tracer.start_as_current_span("catalog_list_products") as span:
            filters = filters or {}
            span.set_attribute("filters.count", len(filters))
            span.set_attribute("page", page)

            try:
                # Start with base queryset, including annotations for average rating and review count
                # The ProductReview model is assumed to be related to Product with 'productreview_set' or similar related_name
                # If not, adjust the filter below (e.g., 'productreview__product')
                # Assuming 'ProductReview' has a foreign key to 'Product' named 'product'
                queryset = (
                    Product.objects.select_related("seller", "category")
                    .prefetch_related("images")
                    .annotate(
                        calculated_average_rating=Subquery(
                            ProductReview.objects.filter(product=OuterRef("pk"))
                            .annotate(avg_rating=Avg("rating"))
                            .values("avg_rating")[:1]
                        ),
                        calculated_review_count=Subquery(
                            ProductReview.objects.filter(product=OuterRef("pk"))
                            .annotate(count_reviews=Count("id"))
                            .values("count_reviews")[:1]
                        ),
                    )
                )

                # Apply filters
                if "category" in filters:
                    queryset = queryset.filter(category__slug=filters["category"])
                    span.set_attribute("filter.category", filters["category"])

                if "seller" in filters:
                    queryset = queryset.filter(seller__id=filters["seller"])

                if "is_active" in filters:
                    queryset = queryset.filter(is_active=filters["is_active"])
                else:
                    # Default to active products only
                    queryset = queryset.filter(is_active=True)

                if "is_featured" in filters:
                    queryset = queryset.filter(is_featured=filters["is_featured"])

                if "min_price" in filters:
                    queryset = queryset.filter(price__gte=filters["min_price"])

                if "max_price" in filters:
                    queryset = queryset.filter(price__lte=filters["max_price"])

                if "condition" in filters:
                    queryset = queryset.filter(condition=filters["condition"])

                if "brand" in filters:
                    queryset = queryset.filter(brand__icontains=filters["brand"])

                if "in_stock" in filters and filters["in_stock"]:
                    queryset = queryset.filter(stock_quantity__gt=0)

                # Apply ordering
                allowed_orderings = ["-created_at", "created_at", "price", "-price", "-view_count", "-favorite_count"]
                if ordering in allowed_orderings:
                    queryset = queryset.order_by(ordering)
                else:
                    queryset = queryset.order_by("-created_at")

                # Paginate
                paginator = Paginator(queryset, page_size)
                page_obj = paginator.get_page(page)

                result_data = {
                    "results": list(page_obj.object_list),
                    "count": paginator.count,
                    "page": page,
                    "page_size": page_size,
                    "num_pages": paginator.num_pages,
                    "has_next": page_obj.has_next(),
                    "has_previous": page_obj.has_previous(),
                }

                span.set_attribute("result.count", paginator.count)

                self.logger.info(f"Listed products: count={paginator.count}, page={page}/{paginator.num_pages}")

                return service_ok(result_data)

            except Exception as e:
                self.logger.error(f"Error listing products: {e}", exc_info=True)
                span.record_exception(e)
                return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    @BaseService.log_performance
    def get_product(self, product_id: str, track_view: bool = True) -> ServiceResult[Product]:
        """
        Get product details by ID.

        Args:
            product_id: Product UUID
            track_view: Whether to increment view count (default: True)

        Returns:
            ServiceResult with Product instance

        Example:
            >>> result = catalog_service.get_product(product_id)
            >>> if result.ok:
            ...     product = result.value
            ...     print(f"Product: {product.name}")
        """
        try:
            product = (
                Product.objects.select_related("seller", "category")
                .prefetch_related("images", "reviews", "reviews__reviewer")
                .get(id=product_id, is_active=True)
            )

            # Track view asynchronously (TODO: Move to Celery task)
            if track_view:
                product.view_count += 1
                product.save(update_fields=["view_count"])

            self.logger.info(f"Retrieved product: {product.name} (id={product_id})")

            return service_ok(product)

        except Product.DoesNotExist:
            return service_err(ErrorCodes.PRODUCT_NOT_FOUND, f"Product {product_id} not found or inactive")
        except Exception as e:
            self.logger.error(f"Error getting product {product_id}: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    @BaseService.log_performance
    def list_categories(self, active_only: bool = True) -> ServiceResult[List[Category]]:
        """
        List all product categories.

        Args:
            active_only: If True, return only active categories

        Returns:
            ServiceResult with list of Category objects
        """
        try:
            queryset = Category.objects.annotate(product_count=Count("products", filter=Q(products__is_active=True)))
            if active_only:
                queryset = queryset.filter(is_active=True)

            categories = list(queryset.order_by("name"))
            return service_ok(categories)
        except Exception as e:
            self.logger.error(f"Error listing categories: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    @BaseService.log_performance
    def get_category(self, slug: str) -> ServiceResult[Category]:
        """
        Get category by slug.

        Args:
            slug: Category slug

        Returns:
            ServiceResult with Category object
        """
        try:
            category = Category.objects.get(slug=slug, is_active=True)
            return service_ok(category)
        except Category.DoesNotExist:
            return service_err(ErrorCodes.NOT_FOUND, f"Category {slug} not found")
        except Exception as e:
            self.logger.error(f"Error getting category {slug}: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    @BaseService.log_performance
    @transaction.atomic
    def create_product(
        self,
        data: Dict[str, Any],
        user: User,
        images: Optional[List] = None,
        image_metadata: Optional[Dict[str, Any]] = None,
    ) -> ServiceResult[Product]:
        """
        Create a new product (seller only).

        Args:
            data: Product data dict
            user: User creating the product (must be seller)
            images: Optional list of image files to upload
            image_metadata: Optional dict with metadata per image
                           Format: {filename: {"alt_text": "...", "is_primary": bool, "order": int}}

        Returns:
            ServiceResult with created Product

        Example:
            >>> result = catalog_service.create_product(
            ...     data={
            ...         "name": "iPhone 15",
            ...         "description": "Latest iPhone",
            ...         "price": "999.00",
            ...         "category_id": category.id,
            ...         "stock_quantity": 10
            ...     },
            ...     user=seller_user,
            ...     images=[image_file1, image_file2],
            ...     image_metadata={"image1.jpg": {"alt_text": "Front view", "is_primary": True, "order": 0}}
            ... )
        """
        try:
            # Validate user is a seller
            if not is_seller(user):
                return service_err(ErrorCodes.PERMISSION_DENIED, "User is not a seller")

            # Get or validate category
            category = data.get("category")
            if not category and "category_id" in data:
                try:
                    category = Category.objects.get(id=data["category_id"], is_active=True)
                except Category.DoesNotExist:
                    self.logger.error(f"Category {data['category_id']} not found for product creation")
                    return service_err(ErrorCodes.INVALID_INPUT, f"Category {data['category_id']} not found")

            # Create product
            product = Product.objects.create(
                name=data["name"],
                description=data.get("description", ""),
                short_description=data.get("short_description", ""),
                seller=user,
                category=category,
                price=data["price"],
                original_price=data.get("original_price"),
                stock_quantity=data.get("stock_quantity", 1),
                condition=data.get("condition", "new"),
                brand=data.get("brand", ""),
                model=data.get("model", ""),
                weight=data.get("weight"),
                dimensions_length=data.get("dimensions_length"),
                dimensions_width=data.get("dimensions_width"),
                dimensions_height=data.get("dimensions_height"),
                colors=data.get("colors", []),
                materials=data.get("materials", ""),
                tags=data.get("tags", []),
                is_digital=data.get("is_digital", False),
            )

            # Handle image uploads if provided
            if images:
                image_upload_result = self._upload_product_images(product, images, image_metadata)
                if not image_upload_result.ok:
                    # Rollback product creation
                    product.delete()
                    return image_upload_result

            self.logger.info(f"Created product: {product.name} (id={product.id}) by seller {user.id}")

            return service_ok(product)

        except Exception as e:
            self.logger.error(f"Error creating product: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    @BaseService.log_performance
    @transaction.atomic
    def update_product(self, product_id: str, data: Dict[str, Any], user: User) -> ServiceResult[Product]:
        """
        Update an existing product (owner only).

        Args:
            product_id: Product UUID
            data: Updated product data
            user: User updating the product

        Returns:
            ServiceResult with updated Product

        Example:
            >>> result = catalog_service.update_product(
            ...     product_id,
            ...     data={"price": "899.00", "stock_quantity": 5},
            ...     user=seller_user
            ... )
        """
        try:
            product = Product.objects.select_for_update().get(id=product_id)

            # Validate ownership
            if product.seller != user:
                return service_err(ErrorCodes.NOT_PRODUCT_OWNER, "You do not own this product")

            # Update allowed fields
            allowed_fields = [
                "name",
                "description",
                "short_description",
                "price",
                "original_price",
                "stock_quantity",
                "condition",
                "brand",
                "model",
                "weight",
                "dimensions_length",
                "dimensions_width",
                "dimensions_height",
                "colors",
                "materials",
                "tags",
                "is_active",
                "is_featured",
            ]

            updated_fields = []
            for field in allowed_fields:
                if field in data:
                    setattr(product, field, data[field])
                    updated_fields.append(field)

            if "category_id" in data:
                try:
                    category = Category.objects.get(id=data["category_id"], is_active=True)
                    product.category = category
                    updated_fields.append("category")
                except Category.DoesNotExist:
                    return service_err(ErrorCodes.INVALID_INPUT, f"Category {data['category_id']} not found")

            product.save(update_fields=updated_fields)

            self.logger.info(f"Updated product: {product.name} (id={product_id}), fields={updated_fields}")

            return service_ok(product)

        except Product.DoesNotExist:
            return service_err(ErrorCodes.PRODUCT_NOT_FOUND, f"Product {product_id} not found")
        except Exception as e:
            self.logger.error(f"Error updating product {product_id}: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    @BaseService.log_performance
    @transaction.atomic
    def delete_product(self, product_id: str, user: User, hard_delete: bool = False) -> ServiceResult[bool]:
        """
        Delete a product (owner only).

        By default, performs soft delete (is_active=False).
        Hard delete permanently removes the product.

        Args:
            product_id: Product UUID
            user: User deleting the product
            hard_delete: If True, permanently delete (default: False)

        Returns:
            ServiceResult with True if deleted

        Example:
            >>> result = catalog_service.delete_product(product_id, user=seller_user)
            >>> if result.ok:
            ...     print("Product deleted")
        """
        try:
            product = Product.objects.select_for_update().get(id=product_id)

            # Validate ownership
            if product.seller != user:
                return service_err(ErrorCodes.NOT_PRODUCT_OWNER, "You do not own this product")

            if hard_delete:
                product_name = product.name
                product.delete()
                self.logger.warning(f"HARD DELETED product: {product_name} (id={product_id}) by user {user.id}")
            else:
                product.is_active = False
                product.save(update_fields=["is_active"])
                self.logger.info(f"Soft deleted product: {product.name} (id={product_id})")

            return service_ok(True)

        except Product.DoesNotExist:
            return service_err(ErrorCodes.PRODUCT_NOT_FOUND, f"Product {product_id} not found")
        except Exception as e:
            self.logger.error(f"Error deleting product {product_id}: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    @BaseService.log_performance
    def search_products(
        self, query: str, filters: Optional[Dict[str, Any]] = None, limit: int = 20
    ) -> ServiceResult[List[Product]]:
        """
        Search products by keyword.

        Searches in: name, description, brand, tags.

        Args:
            query: Search query string
            filters: Optional additional filters
            limit: Maximum results to return

        Returns:
            ServiceResult with list of matching products

        Example:
            >>> result = catalog_service.search_products("iPhone", limit=10)
            >>> if result.ok:
            ...     products = result.value
        """
        try:
            filters = filters or {}

            # Build search query (basic implementation - will be enhanced by SearchService)
            queryset = Product.objects.select_related("seller", "category").prefetch_related("images")

            if query:
                # Search across multiple fields
                search_query = Q(name__icontains=query) | Q(description__icontains=query) | Q(brand__icontains=query)
                queryset = queryset.filter(search_query)

            # Apply standard filters
            queryset = queryset.filter(is_active=filters.get("is_active", True))

            if "category" in filters:
                queryset = queryset.filter(category__slug=filters["category"])

            # Order by relevance (simple: name match first)
            queryset = queryset.order_by("-created_at")[:limit]

            products = list(queryset)

            self.logger.info(f"Search: query='{query}', results={len(products)}")

            return service_ok(products)

        except Exception as e:
            self.logger.error(f"Error searching products: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    def _upload_product_images(
        self, product: Product, images: List, image_metadata: Optional[Dict[str, Any]] = None
    ) -> ServiceResult[List[ProductImage]]:
        """
        Upload product images using storage abstraction.

        Args:
            product: Product instance
            images: List of uploaded file objects
            image_metadata: Optional dict with metadata per image (alt_text, is_primary, order)
                           Format: {filename: {"alt_text": "...", "is_primary": bool, "order": int}}

        Returns:
            ServiceResult with list of created ProductImage instances
        """
        try:
            created_images = []
            image_metadata = image_metadata or {}

            for idx, image_file in enumerate(images):
                # Get metadata for this specific image
                filename = getattr(image_file, "name", f"image_{idx}")
                metadata = image_metadata.get(filename, {})

                # Generate S3 key (use furniture path for proxy compatibility)
                s3_key = f"furniture/{product.seller.id}/{product.id}/{filename}"

                try:
                    # Upload to storage
                    self.storage.upload(
                        file=image_file,
                        path=s3_key,
                        content_type=image_file.content_type if hasattr(image_file, "content_type") else "image/jpeg",
                    )

                    # Create ProductImage record with metadata
                    product_image = ProductImage.objects.create(
                        product=product,
                        s3_key=s3_key,
                        s3_bucket=settings.AWS_STORAGE_BUCKET_NAME,
                        original_filename=filename,
                        image=image_file,  # Save to local storage/ImageField for fallback
                        file_size=image_file.size if hasattr(image_file, "size") else None,
                        content_type=image_file.content_type if hasattr(image_file, "content_type") else "image/jpeg",
                        alt_text=metadata.get("alt_text", ""),
                        is_primary=metadata.get("is_primary", idx == 0),  # Use metadata or default to first
                        order=metadata.get("order", idx),  # Use metadata or default to index
                    )

                    created_images.append(product_image)

                except StorageException as e:
                    self.logger.error(f"Failed to upload image {filename}: {e}")
                    continue

            self.logger.info(f"Uploaded {len(created_images)} images for product {product.id}")

            return service_ok(created_images)

        except Exception as e:
            self.logger.error(f"Error uploading product images: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))
