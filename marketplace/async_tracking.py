"""
Asynchronous tracking system for marketplace activities.

This module provides background task processing for user activity tracking,
allowing the API to return responses immediately while processing metrics
asynchronously for better performance.
"""

import logging
import json
from typing import Optional, List, Dict, Any
from datetime import datetime
from django.core.cache import cache
from django.db import models
from django.contrib.auth import get_user_model
from django.http import HttpRequest
from django.conf import settings
from concurrent.futures import ThreadPoolExecutor
import threading
import queue
import time

User = get_user_model()
logger = logging.getLogger(__name__)

# Global thread pool for background processing
_thread_pool = None
_processing_queue = queue.Queue()
_processing_thread = None


class AsyncTracker:
    """
    Asynchronous tracker that queues tasks for background processing.
    
    This allows the main API response to return immediately while
    metrics processing happens in the background.
    """
    
    @staticmethod
    def initialize():
        """Initialize the async tracking system."""
        global _thread_pool, _processing_thread
        
        if _thread_pool is None:
            _thread_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="async_tracker")
            logger.info("Initialized AsyncTracker thread pool")
        
        if _processing_thread is None or not _processing_thread.is_alive():
            _processing_thread = threading.Thread(
                target=AsyncTracker._background_processor,
                daemon=True,
                name="metrics_processor"
            )
            _processing_thread.start()
            logger.info("Started background metrics processor thread")
    
    @staticmethod
    def _background_processor():
        """Background thread that processes queued tracking tasks."""
        logger.info("Background metrics processor started")
        
        while True:
            try:
                # Get task from queue with timeout
                try:
                    task = _processing_queue.get(timeout=5.0)
                except queue.Empty:
                    continue
                
                # Process the task
                AsyncTracker._process_task(task)
                _processing_queue.task_done()
                
            except Exception as e:
                logger.error(f"Error in background processor: {str(e)}")
                time.sleep(1)  # Brief delay before continuing
    
    @staticmethod
    def _process_task(task: Dict[str, Any]):
        """Process a single tracking task."""
        try:
            task_type = task.get('type')
            task_data = task.get('data', {})
            
            if task_type == 'listing_view':
                AsyncTracker._process_listing_view(task_data)
            elif task_type == 'product_view':
                AsyncTracker._process_product_view(task_data)
            elif task_type == 'product_click':
                AsyncTracker._process_product_click(task_data)
            elif task_type == 'cart_action':
                AsyncTracker._process_cart_action(task_data)
            elif task_type == 'favorite_action':
                AsyncTracker._process_favorite_action(task_data)
            else:
                logger.warning(f"Unknown task type: {task_type}")
                
        except Exception as e:
            logger.error(f"Error processing task {task.get('type', 'unknown')}: {str(e)}")
    
    @staticmethod
    def _process_listing_view(data: Dict[str, Any]):
        """Process listing view tracking in background."""
        try:
            from marketplace.models import Product
            from activity.models import UserClick
            from .tracking_utils import MetricsHelper, SessionHelper
            
            product_ids = data.get('product_ids', [])
            user_id = data.get('user_id')
            session_key = data.get('session_key')
            timestamp = data.get('timestamp')
            request_meta = data.get('request_meta', {})
            
            # Get products
            products = Product.objects.filter(id__in=product_ids, is_active=True)
            
            # Ensure metrics exist (bulk operation)
            MetricsHelper.bulk_ensure_metrics(list(products))
            
            # Get user if authenticated
            user = None
            if user_id:
                try:
                    user = User.objects.get(id=user_id)
                except User.DoesNotExist:
                    pass
            
            # Create a mock request object with stored metadata
            mock_request = AsyncTracker._create_mock_request(request_meta)
            
            # Track views for each product
            tracked_count = 0
            for product in products:
                try:
                    UserClick.track_activity(
                        product=product,
                        action='listing_view',
                        user=user,
                        session_key=session_key,
                        request=mock_request
                    )
                    tracked_count += 1
                except Exception as e:
                    logger.warning(f"Failed to track listing view for product {product.id}: {str(e)}")
                    continue
            
            logger.info(f"Background listing tracking: {tracked_count}/{len(product_ids)} products")
            
        except Exception as e:
            logger.error(f"Error in background listing view processing: {str(e)}")
    
    @staticmethod
    def _process_product_view(data: Dict[str, Any]):
        """Process single product view tracking in background."""
        try:
            from marketplace.models import Product
            from activity.models import UserClick
            from .tracking_utils import MetricsHelper
            
            product_id = data.get('product_id')
            user_id = data.get('user_id')
            session_key = data.get('session_key')
            timestamp = data.get('timestamp')
            request_meta = data.get('request_meta', {})
            
            # Get product
            try:
                product = Product.objects.get(id=product_id, is_active=True)
            except Product.DoesNotExist:
                logger.warning(f"Product {product_id} not found for view tracking")
                return
            
            # Ensure metrics exist
            MetricsHelper.ensure_metrics_exist(product)
            
            # Get user if authenticated
            user = None
            if user_id:
                try:
                    user = User.objects.get(id=user_id)
                except User.DoesNotExist:
                    pass
            
            # Create a mock request object with stored metadata
            mock_request = AsyncTracker._create_mock_request(request_meta)
            
            # Track the view
            UserClick.track_activity(
                product=product,
                action='detail_view',
                user=user,
                session_key=session_key,
                request=mock_request
            )
            
            logger.info(f"Background view tracking: Product {product.name}")
            
        except Exception as e:
            logger.error(f"Error in background product view processing: {str(e)}")
    
    @staticmethod
    def _process_product_click(data: Dict[str, Any]):
        """Process product click tracking in background."""
        try:
            from marketplace.models import Product
            from activity.models import UserClick
            from .tracking_utils import MetricsHelper
            
            product_id = data.get('product_id')
            user_id = data.get('user_id')
            session_key = data.get('session_key')
            timestamp = data.get('timestamp')
            request_meta = data.get('request_meta', {})
            
            # Get product
            try:
                product = Product.objects.get(id=product_id, is_active=True)
            except Product.DoesNotExist:
                logger.warning(f"Product {product_id} not found for click tracking")
                return
            
            # Ensure metrics exist
            MetricsHelper.ensure_metrics_exist(product)
            
            # Get user if authenticated
            user = None
            if user_id:
                try:
                    user = User.objects.get(id=user_id)
                except User.DoesNotExist:
                    pass
            
            # Create a mock request object with stored metadata
            mock_request = AsyncTracker._create_mock_request(request_meta)
            
            # Track the click
            UserClick.track_activity(
                product=product,
                action='click',
                user=user,
                session_key=session_key,
                request=mock_request
            )
            
            logger.info(f"Background click tracking: Product {product.name}")
            
        except Exception as e:
            logger.error(f"Error in background product click processing: {str(e)}")
    
    @staticmethod
    def _process_cart_action(data: Dict[str, Any]):
        """Process cart action tracking in background."""
        try:
            from marketplace.models import Product
            from activity.models import UserClick
            from .tracking_utils import MetricsHelper
            
            product_id = data.get('product_id')
            user_id = data.get('user_id')
            action = data.get('action', 'cart_add')  # cart_add or cart_remove
            quantity = data.get('quantity', 1)
            timestamp = data.get('timestamp')
            request_meta = data.get('request_meta', {})
            
            # Get product and user
            try:
                product = Product.objects.get(id=product_id, is_active=True)
                user = User.objects.get(id=user_id) if user_id else None
            except (Product.DoesNotExist, User.DoesNotExist):
                logger.warning(f"Product {product_id} or user {user_id} not found for cart tracking")
                return
            
            if not user:
                logger.warning("Cart tracking requires authenticated user")
                return
            
            # Ensure metrics exist
            MetricsHelper.ensure_metrics_exist(product)
            
            # Create a mock request object with stored metadata
            mock_request = AsyncTracker._create_mock_request(request_meta)
            
            # Track the cart action
            UserClick.track_activity(
                product=product,
                action=action,
                user=user,
                request=mock_request
            )
            
            logger.info(f"Background cart tracking: {action} {quantity}x {product.name}")
            
        except Exception as e:
            logger.error(f"Error in background cart action processing: {str(e)}")
    
    @staticmethod
    def _process_favorite_action(data: Dict[str, Any]):
        """Process favorite action tracking in background."""
        try:
            from marketplace.models import Product
            from activity.models import UserClick
            from .tracking_utils import MetricsHelper
            
            product_id = data.get('product_id')
            user_id = data.get('user_id')
            action = data.get('action', 'favorite')  # favorite or unfavorite
            timestamp = data.get('timestamp')
            request_meta = data.get('request_meta', {})
            
            # Get product and user
            try:
                product = Product.objects.get(id=product_id, is_active=True)
                user = User.objects.get(id=user_id) if user_id else None
            except (Product.DoesNotExist, User.DoesNotExist):
                logger.warning(f"Product {product_id} or user {user_id} not found for favorite tracking")
                return
            
            if not user:
                logger.warning("Favorite tracking requires authenticated user")
                return
            
            # Ensure metrics exist
            MetricsHelper.ensure_metrics_exist(product)
            
            # Create a mock request object with stored metadata
            mock_request = AsyncTracker._create_mock_request(request_meta)
            
            # Track the favorite action
            UserClick.track_activity(
                product=product,
                action=action,
                user=user,
                request=mock_request
            )
            
            logger.info(f"Background favorite tracking: {action} {product.name}")
            
        except Exception as e:
            logger.error(f"Error in background favorite action processing: {str(e)}")
    
    @staticmethod
    def queue_listing_view(products: List, request: HttpRequest) -> bool:
        """
        Queue listing view tracking for background processing.
        
        Args:
            products: List of Product instances
            request: HTTP request
            
        Returns:
            bool: True if queued successfully
        """
        try:
            AsyncTracker.initialize()
            
            # Extract user and session info
            user_id = request.user.id if request.user.is_authenticated else None
            session_key = None
            
            if not user_id:
                if not request.session.session_key:
                    request.session.save()
                session_key = request.session.session_key
            
            # Prepare task data
            task_data = {
                'product_ids': [product.id for product in products],
                'user_id': user_id,
                'session_key': session_key,
                'timestamp': datetime.now().isoformat(),
                'request_meta': AsyncTracker._extract_request_meta(request)
            }
            
            # Queue the task
            task = {
                'type': 'listing_view',
                'data': task_data
            }
            
            _processing_queue.put(task)
            logger.debug(f"Queued listing view tracking for {len(products)} products")
            return True
            
        except Exception as e:
            logger.error(f"Error queuing listing view tracking: {str(e)}")
            return False
    
    @staticmethod
    def queue_product_view(product, request: HttpRequest) -> bool:
        """
        Queue product view tracking for background processing.
        
        Args:
            product: Product instance
            request: HTTP request
            
        Returns:
            bool: True if queued successfully
        """
        try:
            AsyncTracker.initialize()
            
            # Extract user and session info
            user_id = request.user.id if request.user.is_authenticated else None
            session_key = None
            
            if not user_id:
                if not request.session.session_key:
                    request.session.save()
                session_key = request.session.session_key
            
            # Prepare task data
            task_data = {
                'product_id': product.id,
                'user_id': user_id,
                'session_key': session_key,
                'timestamp': datetime.now().isoformat(),
                'request_meta': AsyncTracker._extract_request_meta(request)
            }
            
            # Queue the task
            task = {
                'type': 'product_view',
                'data': task_data
            }
            
            _processing_queue.put(task)
            logger.debug(f"Queued product view tracking for {product.name}")
            return True
            
        except Exception as e:
            logger.error(f"Error queuing product view tracking: {str(e)}")
            return False
    
    @staticmethod
    def queue_product_click(product, request: HttpRequest) -> bool:
        """
        Queue product click tracking for background processing.
        
        Args:
            product: Product instance
            request: HTTP request
            
        Returns:
            bool: True if queued successfully
        """
        try:
            AsyncTracker.initialize()
            
            # Extract user and session info
            user_id = request.user.id if request.user.is_authenticated else None
            session_key = None
            
            if not user_id:
                if not request.session.session_key:
                    request.session.save()
                session_key = request.session.session_key
            
            # Prepare task data
            task_data = {
                'product_id': product.id,
                'user_id': user_id,
                'session_key': session_key,
                'timestamp': datetime.now().isoformat(),
                'request_meta': AsyncTracker._extract_request_meta(request)
            }
            
            # Queue the task
            task = {
                'type': 'product_click',
                'data': task_data
            }
            
            _processing_queue.put(task)
            logger.debug(f"Queued product click tracking for {product.name}")
            return True
            
        except Exception as e:
            logger.error(f"Error queuing product click tracking: {str(e)}")
            return False
    
    @staticmethod
    def queue_cart_action(product, user, action: str, quantity: int = 1, request: HttpRequest = None) -> bool:
        """
        Queue cart action tracking for background processing.
        
        Args:
            product: Product instance
            user: User instance
            action: 'cart_add' or 'cart_remove'
            quantity: Quantity affected
            request: HTTP request
            
        Returns:
            bool: True if queued successfully
        """
        try:
            AsyncTracker.initialize()
            
            if not user:
                logger.warning("Cart action tracking requires authenticated user")
                return False
            
            # Prepare task data
            task_data = {
                'product_id': product.id,
                'user_id': user.id,
                'action': action,
                'quantity': quantity,
                'timestamp': datetime.now().isoformat(),
                'request_meta': AsyncTracker._extract_request_meta(request) if request else {}
            }
            
            # Queue the task
            task = {
                'type': 'cart_action',
                'data': task_data
            }
            
            _processing_queue.put(task)
            logger.debug(f"Queued cart action tracking: {action} {quantity}x {product.name}")
            return True
            
        except Exception as e:
            logger.error(f"Error queuing cart action tracking: {str(e)}")
            return False
    
    @staticmethod
    def queue_favorite_action(product, user, action: str, request: HttpRequest = None) -> bool:
        """
        Queue favorite action tracking for background processing.
        
        Args:
            product: Product instance
            user: User instance
            action: 'favorite' or 'unfavorite'
            request: HTTP request
            
        Returns:
            bool: True if queued successfully
        """
        try:
            AsyncTracker.initialize()
            
            if not user:
                logger.warning("Favorite action tracking requires authenticated user")
                return False
            
            # Prepare task data
            task_data = {
                'product_id': product.id,
                'user_id': user.id,
                'action': action,
                'timestamp': datetime.now().isoformat(),
                'request_meta': AsyncTracker._extract_request_meta(request) if request else {}
            }
            
            # Queue the task
            task = {
                'type': 'favorite_action',
                'data': task_data
            }
            
            _processing_queue.put(task)
            logger.debug(f"Queued favorite action tracking: {action} {product.name}")
            return True
            
        except Exception as e:
            logger.error(f"Error queuing favorite action tracking: {str(e)}")
            return False
    
    @staticmethod
    def _extract_request_meta(request: Optional[HttpRequest]) -> Dict[str, Any]:
        """Extract relevant metadata from HTTP request."""
        if not request:
            return {}
        
        try:
            return {
                'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                'ip_address': AsyncTracker._get_client_ip(request),
                'referer': request.META.get('HTTP_REFERER', ''),
                'method': request.method,
                'path': request.path,
            }
        except Exception as e:
            logger.warning(f"Error extracting request metadata: {str(e)}")
            return {}
    
    @staticmethod
    def _get_client_ip(request: HttpRequest) -> str:
        """Get client IP address from request."""
        try:
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip = x_forwarded_for.split(',')[0]
            else:
                ip = request.META.get('REMOTE_ADDR')
            return ip or ''
        except Exception:
            return ''
    
    @staticmethod
    def _create_mock_request(request_meta: Dict[str, Any]):
        """Create a mock request object from stored metadata."""
        class MockRequest:
            def __init__(self, meta_data):
                self.META = {
                    'HTTP_USER_AGENT': meta_data.get('user_agent', ''),
                    'REMOTE_ADDR': meta_data.get('ip_address', ''),
                    'HTTP_REFERER': meta_data.get('referer', ''),
                }
                self.method = meta_data.get('method', 'GET')
                self.path = meta_data.get('path', '/')
        
        return MockRequest(request_meta)
    
    @staticmethod
    def get_queue_status() -> Dict[str, Any]:
        """Get status information about the async tracking system."""
        try:
            return {
                'queue_size': _processing_queue.qsize() if _processing_queue else 0,
                'thread_pool_active': _thread_pool is not None,
                'processor_thread_alive': _processing_thread.is_alive() if _processing_thread else False,
                'processor_thread_name': _processing_thread.name if _processing_thread else None
            }
        except Exception as e:
            logger.error(f"Error getting queue status: {str(e)}")
            return {'error': str(e)}


# Initialize the async tracker when module is imported
try:
    AsyncTracker.initialize()
except Exception as e:
    logger.error(f"Failed to initialize AsyncTracker: {str(e)}")