# Activity Tracking System

## Overview

The activity tracking system monitors user interactions with products in the marketplace. It automatically tracks views, favorites, cart additions, and other activities to provide detailed analytics and improve product metrics.

## Features

- 🔍 **Product Views**: Automatic tracking when users view product details
- ❤️ **Favorites**: Track when users add/remove products from favorites
- 🛒 **Cart Actions**: Monitor cart additions and removals
- 👆 **Clicks**: Record product clicks for interaction analytics
- 👤 **User & Anonymous Tracking**: Support for both authenticated and anonymous users
- 📊 **Real-time Metrics**: Automatic updates to ProductMetrics model
- 📈 **Analytics**: Daily/weekly/monthly activity summaries

## Architecture

### Models

1. **UserClick**: Core activity tracking model
   - Tracks individual user interactions
   - Supports anonymous users via session keys
   - Stores request metadata (IP, user agent, referer)

2. **ActivitySummary**: Aggregated analytics
   - Daily, weekly, monthly summaries
   - Unique user/session counts
   - Performance analytics

3. **ProductMetrics**: Enhanced metrics (existing model)
   - Real-time counters updated by activity system
   - Conversion rate calculations
   - Legacy field support maintained

### Activity Types

| Action | Description | Triggered By |
|--------|-------------|--------------|
| `view` | Product detail page view | Product retrieve API call |
| `click` | Product click/interaction | Product click API call |
| `favorite` | Add to favorites | Favorite API call |
| `unfavorite` | Remove from favorites | Unfavorite API call |
| `cart_add` | Add to cart | Cart add_item API call |
| `cart_remove` | Remove from cart | Cart remove_item API call |

## API Endpoints

### Track Activity
```http
POST /api/activity/track/
Content-Type: application/json

{
    "product_id": "uuid-here",
    "action": "view"
}
```

**Response:**
```json
{
    "success": true,
    "message": "Activity tracked: view on Product Name",
    "activity_id": 123,
    "user_authenticated": true,
    "session_key": null
}
```

### Get Product Statistics
```http
GET /api/activity/stats/{product_id}/
```

**Response:**
```json
{
    "product_id": "uuid-here",
    "product_name": "Product Name",
    "activity_counts": {
        "view": 150,
        "click": 45,
        "favorite": 12,
        "unfavorite": 2,
        "cart_add": 8,
        "cart_remove": 1
    },
    "metrics": {
        "total_views": 150,
        "total_clicks": 45,
        "total_favorites": 10,
        "total_cart_additions": 8,
        "view_to_click_rate": 30.0,
        "click_to_cart_rate": 17.8,
        "cart_to_purchase_rate": 0.0,
        "last_updated": "2024-01-15T10:30:00Z"
    }
}
```

### Get User Activity History
```http
GET /api/activity/history/?action=view&limit=50
Authorization: Bearer <token>
```

**Response:**
```json
{
    "activities": [
        {
            "id": 123,
            "product_id": "uuid-here",
            "product_name": "Product Name",
            "action": "view",
            "created_at": "2024-01-15T10:30:00Z",
            "ip_address": "192.168.1.1"
        }
    ],
    "total_count": 1
}
```

## Integration

### Automatic Tracking

The system automatically tracks activities in existing marketplace views:

1. **Product Views**: `ProductViewSet.retrieve()` - Tracks 'view' action
2. **Product Favorites**: `ProductViewSet.favorite()` - Tracks 'favorite'/'unfavorite'
3. **Product Clicks**: `ProductViewSet.click()` - Tracks 'click' action
4. **Cart Operations**: `CartViewSet.add_item()` and `remove_item()` - Tracks cart actions

### Manual Tracking

Use the activity tracking API for custom implementations:

```python
from activity.models import UserClick

# Track activity manually
UserClick.track_activity(
    product=product_instance,
    action='view',
    user=request.user,  # None for anonymous
    session_key=request.session.session_key,  # For anonymous users
    request=request  # For metadata extraction
)
```

### Frontend Integration

```javascript
// Track custom activity from frontend
const trackActivity = async (productId, action) => {
    try {
        const response = await fetch('/api/activity/track/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${authToken}` // Optional for authenticated users
            },
            body: JSON.stringify({
                product_id: productId,
                action: action
            })
        });
        
        const data = await response.json();
        console.log('Activity tracked:', data);
    } catch (error) {
        console.error('Failed to track activity:', error);
    }
};

// Usage examples
trackActivity('product-uuid', 'view');
trackActivity('product-uuid', 'click');
```

## Data Flow

1. **User Interaction** → Marketplace API call
2. **API View** → Calls `UserClick.track_activity()`
3. **Activity Record** → Created in database
4. **Metrics Update** → ProductMetrics automatically updated
5. **Analytics** → ActivitySummary generation (scheduled task)

## Analytics & Reporting

### Conversion Rates

The system automatically calculates:
- **View-to-Click Rate**: (total_clicks / total_views) × 100
- **Click-to-Cart Rate**: (total_cart_additions / total_clicks) × 100
- **Cart-to-Purchase Rate**: (total_sales / total_cart_additions) × 100

### Activity Summaries

Generate daily summaries for analytics:

```python
from activity.models import ActivitySummary
from datetime import date

# Generate daily summary for a product
summary = ActivitySummary.generate_daily_summary(
    product=product_instance,
    date=date.today()
)
```

## Database Optimization

### Indexes

The system includes optimized database indexes:
- `(product, action, created_at)` - For product-specific queries
- `(user, action, created_at)` - For user activity queries
- `(session_key, action, created_at)` - For anonymous user queries
- `(created_at)` - For time-based queries

### Performance Considerations

1. **Bulk Operations**: Use `bulk_create()` for importing historical data
2. **Archival**: Consider archiving old activity records (>1 year)
3. **Caching**: Cache frequently accessed metrics
4. **Async Processing**: Consider async task queues for heavy analytics

## Admin Interface

The Django admin provides:
- **UserClick Admin**: Browse and filter activity records
- **ActivitySummary Admin**: View aggregated analytics
- **Search & Filtering**: By product, user, action, date range
- **Export Capabilities**: CSV export for external analysis

## Migration & Setup

1. **Add to Settings**: Activity app already added to `INSTALLED_APPS`
2. **Run Migrations**: 
   ```bash
   python manage.py migrate activity
   ```
3. **Create Superuser**: Access admin interface
4. **Start Tracking**: Activities are tracked automatically

## Monitoring

### Health Checks

Monitor the system health:
- Activity record creation rate
- Failed tracking attempts
- Database performance
- Metrics update accuracy

### Alerts

Set up alerts for:
- High error rates in activity tracking
- Unusual activity patterns
- Database performance degradation
- Missing activity records

## Privacy & GDPR

### Data Collection

The system collects:
- User IDs (for authenticated users)
- Session keys (for anonymous users)
- IP addresses
- User agents
- Referrer URLs
- Timestamps

### Compliance Features

- **Anonymous Tracking**: Support for tracking without user identification
- **Data Retention**: Configurable retention periods
- **Data Export**: User activity export capabilities
- **Data Deletion**: Cascade deletion when users are deleted

### Configuration

```python
# settings.py
ACTIVITY_TRACKING = {
    'RETENTION_DAYS': 365,  # Keep activity records for 1 year
    'TRACK_ANONYMOUS': True,  # Track anonymous users
    'COLLECT_IP': True,  # Collect IP addresses
    'COLLECT_USER_AGENT': True,  # Collect user agents
}
```

## Troubleshooting

### Common Issues

1. **Activities Not Being Tracked**
   - Check if activity app is in INSTALLED_APPS
   - Verify migrations have been run
   - Check error logs for exceptions

2. **Metrics Not Updating**
   - Verify ProductMetrics records exist
   - Check the `update_product_metrics()` method
   - Monitor database transaction rollbacks

3. **Performance Issues**
   - Review database indexes
   - Consider archiving old records
   - Monitor query performance

### Debug Mode

Enable debug logging:

```python
# settings.py
LOGGING['loggers']['activity'] = {
    'handlers': ['console', 'file'],
    'level': 'DEBUG',
    'propagate': True,
}
```

## Future Enhancements

- 📱 **Mobile App Integration**: Track activities from mobile apps
- 🤖 **Machine Learning**: Predictive analytics and recommendations
- 📊 **Advanced Analytics**: Cohort analysis, funnel analytics
- 🔄 **Real-time Streaming**: WebSocket-based real-time updates
- 📈 **A/B Testing**: Integration with experimentation platforms