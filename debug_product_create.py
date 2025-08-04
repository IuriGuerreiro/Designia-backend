#!/usr/bin/env python3
"""
Debug script to test product creation with detailed logging
Run this with: python manage.py shell < debug_product_create.py
"""

import os
import django
import logging

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'designiaBackend.settings')
django.setup()

from django.contrib.auth import get_user_model
from marketplace.models import Category, Product
from marketplace.serializers import ProductCreateUpdateSerializer
from django.test import RequestFactory

# Set up logging to see our debug output
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('marketplace.serializers')

User = get_user_model()
factory = RequestFactory()

def test_product_creation():
    print("=== DJANGO DEBUG TEST START ===")
    
    # Get or create a test user
    user, created = User.objects.get_or_create(
        email='test@example.com',
        defaults={
            'username': 'testuser',
            'first_name': 'Test',
            'last_name': 'User'
        }
    )
    print(f"Test user: {user.email} (created: {created})")
    
    # Get or create a test category
    category, created = Category.objects.get_or_create(
        name='Test Category',
        defaults={'slug': 'test-category'}
    )
    print(f"Test category: {category.name} (created: {created})")
    
    # Test data that matches what the frontend sends
    test_data = {
        'name': 'Test Product',
        'description': 'A test product description',
        'short_description': 'Short test description',
        'price': '299.99',
        'original_price': '',
        'stock_quantity': '10',
        'category': str(category.id),
        'condition': 'new',
        'brand': 'Test Brand',
        'model': 'Test Model',
        'weight': '5.5',
        'dimensions_length': '100',
        'dimensions_width': '50',
        'dimensions_height': '30',
        'materials': 'Wood, Metal',
        'colors': '["Red", "Blue"]',  # JSON string
        'tags': '["furniture", "modern"]',  # JSON string
        'is_featured': 'false',
        'is_digital': 'false',
    }
    
    print(f"Test data: {test_data}")
    
    # Create a mock request
    request = factory.post('/api/marketplace/products/', test_data)
    request.user = user
    
    # Test serializer
    try:
        serializer = ProductCreateUpdateSerializer(data=test_data, context={'request': request})
        print(f"Serializer is_valid: {serializer.is_valid()}")
        
        if not serializer.is_valid():
            print(f"Serializer errors: {serializer.errors}")
        else:
            product = serializer.save()
            print(f"Product created: {product.name} (ID: {product.id})")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    
    print("=== DJANGO DEBUG TEST END ===")

if __name__ == '__main__':
    test_product_creation()