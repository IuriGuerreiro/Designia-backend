from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from marketplace.models import Product
from .models import UserClick
from .serializers import ActivityTrackingSerializer, UserClickSerializer


@api_view(['POST'])
@permission_classes([IsAuthenticatedOrReadOnly])
def track_product_activity(request):
    """
    Track user activity on products.
    
    Expected payload:
    {
        "product_id": "uuid",
        "action": "view|click|favorite|unfavorite|cart_add|cart_remove"
    }
    """
    try:
        # Validate input data
        serializer = ActivityTrackingSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'error': 'Invalid input data',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        product_id = serializer.validated_data['product_id']
        action = serializer.validated_data['action']
        
        # Get product
        try:
            product = Product.objects.get(id=product_id, is_active=True)
        except Product.DoesNotExist:
            return Response({
                'error': 'Product not found or inactive'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get user and session info
        user = request.user if request.user.is_authenticated else None
        session_key = request.session.session_key if not user else None
        
        # Ensure session key exists for anonymous users
        if not user and not session_key:
            request.session.save()
            session_key = request.session.session_key
        
        # Track the activity
        activity = UserClick.track_activity(
            product=product,
            action=action,
            user=user,
            session_key=session_key,
            request=request
        )
        
        return Response({
            'success': True,
            'message': f'Activity tracked: {action} on {product.name}',
            'activity_id': activity.id,
            'user_authenticated': user is not None,
            'session_key': session_key if not user else None
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response({
            'error': f'Failed to track activity: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticatedOrReadOnly])
def get_product_activity_stats(request, product_id):
    """
    Get activity statistics for a specific product.
    """
    try:
        product = get_object_or_404(Product, id=product_id, is_active=True)
        
        # Get activity counts
        activity_counts = {}
        for action, _ in UserClick.ACTION_CHOICES:
            activity_counts[action] = UserClick.objects.filter(
                product=product,
                action=action
            ).count()
        
        # Get product metrics if available
        metrics_data = {}
        if hasattr(product, 'metrics'):
            metrics = product.metrics
            metrics_data = {
                'total_views': metrics.total_views,
                'total_clicks': metrics.total_clicks,
                'total_favorites': metrics.total_favorites,
                'total_cart_additions': metrics.total_cart_additions,
                'view_to_click_rate': metrics.view_to_click_rate,
                'click_to_cart_rate': metrics.click_to_cart_rate,
                'cart_to_purchase_rate': metrics.cart_to_purchase_rate,
                'last_updated': metrics.last_updated
            }
        
        return Response({
            'product_id': product.id,
            'product_name': product.name,
            'activity_counts': activity_counts,
            'metrics': metrics_data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': f'Failed to get activity stats: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticatedOrReadOnly])
def get_user_activity_history(request):
    """
    Get activity history for the authenticated user.
    """
    try:
        if not request.user.is_authenticated:
            return Response({
                'error': 'Authentication required'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Get query parameters
        action_filter = request.GET.get('action')
        limit = int(request.GET.get('limit', 50))
        
        # Build query
        activities = UserClick.objects.filter(user=request.user).select_related('product')
        
        if action_filter:
            activities = activities.filter(action=action_filter)
        
        activities = activities[:limit]
        
        # Format response
        activity_data = []
        for activity in activities:
            activity_data.append({
                'id': activity.id,
                'product_id': activity.product.id,
                'product_name': activity.product.name,
                'action': activity.action,
                'created_at': activity.created_at,
                'ip_address': activity.ip_address
            })
        
        return Response({
            'activities': activity_data,
            'total_count': len(activity_data)
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': f'Failed to get activity history: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)