# Marketplace API

**Base path:** `/api/marketplace/`

## Categories

| Method | Path | Description | Request | Success Response |
| --- | --- | --- | --- | --- |
| GET | `/categories/` | List active categories (searchable by `name`, `description`). | Optional `search` query. | `200 OK` list of categories with nested active subcategories and counts. |
| GET | `/categories/{slug}/` | Retrieve category details. | Path `slug`. | `200 OK` with category info. |
| GET | `/categories/{slug}/products/` | List active products within the category, applying standard product filters. | Path `slug`, optional query filters (same as product list). | `200 OK` list of `ProductListSerializer` entries with activity tracking performed in background. |

## Products

`ProductViewSet` supports standard REST operations plus custom actions.

| Method | Path | Description | Request | Success Response |
| --- | --- | --- | --- | --- |
| GET | `/products/` | Filterable/paginatable product listing. | Query params: filtering handled by `ProductFilter` (category, price ranges, tags, etc.), search via `search`, ordering via `ordering`. | `200 OK` array of `ProductListSerializer` items with seller + primary image metadata. |
| POST | `/products/` | Create a product (seller/admin only). | Auth header. FormData or JSON accepted by `ProductCreateUpdateSerializer`; image uploads via `main_image`, `images`, or `uploaded_images` fields. Requires seller role. | `201 Created` with product payload plus uploaded image metadata. |
| GET | `/products/{slug}/` | Product detail. | Path `slug`. | `200 OK` `ProductDetailSerializer`; triggers async view tracking. |
| PATCH | `/products/{slug}/` | Partial update (seller/admin). | Auth header. Same payload rules as create; boolean fields accept string equivalents. | `200 OK` with updated product. |
| DELETE | `/products/{slug}/` | Soft delete/deactivate product (seller/admin). | Auth header. | `204 No Content` on success. |
| POST | `/products/{slug}/favorite/` | Toggle favorite for current user. | Auth header. | `200 OK`/`201` with `{favorited: bool}`. |
| POST | `/products/{slug}/click/` | Record a click event (auth optional). | Optional auth. | `200 OK` with `{clicked: true}`. |
| GET | `/products/{slug}/reviews/` | List active reviews for the product. | Path `slug`. | `200 OK` array of reviews. |
| POST | `/products/{slug}/add_review/` | Create review (one per user/product). | Auth header. JSON: `rating`, `title`, `comment`. | `201 Created` with review data. |
| GET | `/products/{slug}/images/` | Retrieve S3 image metadata for product (requires S3). | Auth optional. | `200 OK` with list of image keys or `images: []` if disabled. |
| POST | `/products/{slug}/upload_image/` | Upload additional product image (seller only, S3). | Auth header. Multipart `image`, optional `image_type` (`main`, `gallery`, `thumbnail`). | `201 Created` with upload details. |
| DELETE | `/products/{slug}/delete_image/` | Remove a single product image (seller only). | Auth header. JSON: `image_key`. | `200 OK` with `deleted_key`. |
| DELETE | `/products/{slug}/delete_all_images/` | Remove all product images (seller only). | Auth header. | `200 OK` with `deleted_count`. |
| GET | `/products/{slug}/main_image/` | Fetch main product image with presigned URL. | Path `slug`. | `200 OK` with `main_image` metadata or message when absent. |
| GET | `/products/{slug}/images_with_presigned_urls/` | Return all images including presigned URLs. | Path `slug`. | `200 OK` with list plus `primary_image`. |
| GET | `/products/{slug}/images/{id}/` | (Manual route) Retrieve single image resource via `ProductImageViewSet`. | Auth optional. | Standard DRF response for product image. |
| PUT | `/products/{slug}/images/{id}/` | Update image metadata/order (owner only). | Auth header. JSON per `ProductImageSerializer`. | Updated record. |
| DELETE | `/products/{slug}/images/{id}/` | Delete image record (owner only). | Auth header. | `204 No Content`. |
| GET | `/products/{slug}/reviews/{id}/` | Retrieve review record. | Auth optional. | `200 OK`. |
| PUT/PATCH | `/products/{slug}/reviews/{id}/` | Update review (owner only). | Auth header. | Updated review. |
| DELETE | `/products/{slug}/reviews/{id}/` | Remove review (owner or admin). | Auth header. | `204 No Content`. |
| GET | `/products/{slug}/images/` | (ViewSet list) alias of manual route; returns ordered image list. | | |
| GET | `/products/{slug}/reviews/` | (ViewSet list) alias of manual route; returns reviews. | | |
| GET | `/products/favorites/` | List current user's favorites. | Auth header. | `200 OK` with `ProductFavoriteSerializer` entries. |
| GET | `/products/my_products/` | List products created by current seller. | Auth header (seller). | `200 OK` product list. |

## Product Images & Reviews (nested routers)

- `GET/POST /products/{slug}/images/` and `/{id}/` map to `ProductImageViewSet`. Creation requires seller ownership.
- `GET/POST /products/{slug}/reviews/` and `/{id}/` map to `ProductReviewViewSet`. Creation requires auth and uniqueness per user/product.

## Cart

Routes are exposed under `/cart/` via `CartViewSet`.

| Method | Path | Description | Request | Success Response |
| --- | --- | --- | --- | --- |
| GET | `/cart/` | Retrieve current cart. | Auth header. | `200 OK` with `CartSerializer` (items, totals, etc.). |
| POST | `/cart/add_item/` | Add or increment a product in cart. | Auth header. JSON: `product_id`, `quantity`. | `200 OK` or `201 Created` with updated `item`, `was_created` flag. Stock checks enforced. |
| PATCH | `/cart/update_item/` | Set quantity for existing cart item. | Auth header. JSON: `item_id`, `quantity`. | `200 OK` with updated item or removal message when quantity <= 0. |
| DELETE | `/cart/remove_item/` | Delete a specific cart item. | Auth header. JSON: `item_id`. | `200 OK` with confirmation. |
| DELETE | `/cart/clear/` | Empty the cart. | Auth header. | `200 OK`. |
| PATCH | `/cart/update_item_status/` | Update local status tag for UI (no persistence). | Auth header. JSON: `item_id`, `status`. | `200 OK` echoing status. |
| POST | `/cart/validate_stock/` | Validate availability for all cart items. | Auth header. | `200 OK` with validation summary per item. |

## Orders

Routes under `/orders/` via `OrderViewSet`.

| Method | Path | Description | Request | Success Response |
| --- | --- | --- | --- | --- |
| GET | `/orders/` | List orders where user is buyer or seller. | Auth header. | `200 OK` array of orders with nested items and shipping info. |
| POST | `/orders/` | Create order manually (rare, normally checkout handles). | Auth header. Body per `OrderSerializer`. | `201 Created` new order. |
| GET | `/orders/{id}/` | Retrieve order detail. | Auth header. | `200 OK` order data. |
| PATCH | `/orders/{id}/` | Update order (limited usage). | Auth header. | Updated order. |
| DELETE | `/orders/{id}/` | Delete order (admin use). | Auth header. | `204 No Content`. |
| GET | `/orders/my_orders/` | Orders where user is buyer. | Auth header. | `200 OK`. |
| PATCH | `/orders/{id}/update_status/` | Simplified status update (seller/buyer as permitted). | Auth header. JSON: `status`. | `200 OK` with new status, validations enforced. |
| PATCH | `/orders/{id}/update_tracking/` | Add/update tracking for seller's items. | Auth header. JSON: `tracking_number` (required), optional `shipping_carrier`. | `200 OK` with order + shipping info summary. |
| GET | `/orders/{id}/tracking_info/` | View all tracking records for the order. | Auth header (buyer, seller, or staff). | `200 OK` with seller-specific tracking entries. |
| GET | `/orders/seller_orders/` | Orders filtered to items sold by current seller. | Auth header (seller). Optional query `status`. | `200 OK` array of orders restricted to seller's items. |
| PATCH | `/orders/{id}/cancel_order/` | Seller cancel with reason. | Auth header. JSON: `cancellation_reason`. | `200 OK` with updated order. |
| PATCH | `/orders/{id}/process_order/` | Move order into `awaiting_shipment` (seller). | Auth header. | `200 OK`. |
| PATCH | `/orders/{id}/update_order_status/` | Advanced status transition with validation. | Auth header. JSON: `status`. | `200 OK` with transition summary. |
| PATCH | `/orders/{id}/update_carrier_code/` | Store carrier codes before shipment. | Auth header. JSON: `carrier_code`, optional `shipping_carrier`. | `200 OK` with order summary. |

## Metrics & Seller Dashboards

Routes under `/metrics/` via `ProductMetricsViewSet` (seller-only).

| Method | Path | Description | Request | Success Response |
| --- | --- | --- | --- | --- |
| GET | `/metrics/` | List metrics for seller's products. | Auth header (seller). | `200 OK` array of `ProductMetricsSerializer`. |
| GET | `/metrics/{id}/` | Retrieve metrics for specific product metrics record. | Auth header. | `200 OK`. |
| GET | `/metrics/dashboard_metrics/` | Aggregated seller dashboard numbers. | Auth header. | `200 OK` with totals (`views`, `clicks`, `revenue`, `recent_orders`, etc.). |
| GET | `/metrics/product_metrics/{product_slug}/` | Metrics for a specific product by slug. | Auth header. Path `product_slug`. | `200 OK` with product info, metrics, recent orders. |

## User Profile Helpers

Routes under `/profiles/` via `UserProfileViewSet` (auth required).

| Method | Path | Description | Request | Success Response |
| --- | --- | --- | --- | --- |
| GET | `/profiles/profile_picture/` | Fetch authenticated user's profile picture from S3. | Auth header. | `200 OK` with `profile_picture` metadata or `None`. |
| POST | `/profiles/upload_profile_picture/` | Upload/replace profile picture (S3). | Auth header. Multipart `profile_picture` or `image` (<=5 MB). | `201 Created` with S3 info. |
| DELETE | `/profiles/delete_profile_picture/` | Delete stored profile picture. | Auth header. | `200 OK` when removed, `404` if none. |
| PATCH | `/profiles/update_profile_picture/` | Alias for upload (accepts same payload). | Auth header. | `201 Created` with S3 info. |

## Public Seller Profile

| Method | Path | Description | Request | Success Response |
| --- | --- | --- | --- | --- |
| GET | `/sellers/{seller_id}/` | Public endpoint showing seller stats, product list, and recent reviews. | Path integer `seller_id`. Auth optional. | `200 OK` with `seller`, `stats`, arrays of `products` and `reviews`. Returns `404` if user is not a seller. |
