# Activity API

**Base path:** `/api/activity/`

| Method | Path | Description | Request | Success Response |
| --- | --- | --- | --- | --- |
| POST | `/track/` | Track a product interaction (view, click, favorite, cart actions). | JSON: `product_id` (UUID), `action` (`view`, `click`, `favorite`, `unfavorite`, `cart_add`, `cart_remove`). Anonymous users rely on session cookie. | `201 Created` with `success`, `message`, `activity_id`, `user_authenticated`, and optional `session_key`. `400` on validation error, `404` if product missing. |
| GET | `/stats/{product_id}/` | Aggregate activity metrics for a product. | Path: `product_id` (UUID). | `200 OK` with `product_id`, `product_name`, dict of `activity_counts`, and optional `metrics` (if `Product.metrics` exists). `404` if product inactive. |
| GET | `/history/` | Fetch recent activity for the authenticated user. | Query params: optional `action` to filter (same values as `track`), optional `limit` (default `50`). | `200 OK` with `activities` array (`id`, `product_id`, `product_name`, `action`, `created_at`, `ip_address`) and `total_count`. Returns `401` if unauthenticated. |
