"""
Django management command to populate the marketplace with sample data
Usage: python manage.py populate_sample_data
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.utils.text import slugify
from decimal import Decimal
import requests
import tempfile
import os

from marketplace.models import Category, Product, ProductImage

User = get_user_model()


class Command(BaseCommand):
    help = 'Populate the marketplace with sample data for testing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing data before populating',
        )
        parser.add_argument(
            '--users',
            type=int,
            default=5,
            help='Number of sample users to create',
        )
        parser.add_argument(
            '--products',
            type=int,
            default=20,
            help='Number of sample products to create',
        )

    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write('Clearing existing data...')
            Product.objects.all().delete()
            Category.objects.all().delete()
            # Don't delete users to preserve auth data

        self.stdout.write('Creating sample data...')
        
        # Create categories
        categories = self.create_categories()
        
        # Create sample users (sellers)
        sellers = self.create_sample_users(options['users'])
        
        # Create products
        self.create_sample_products(categories, sellers, options['products'])
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully populated database with sample data!\n'
                f'- {len(categories)} categories\n'
                f'- {len(sellers)} sellers\n'
                f'- {options["products"]} products'
            )
        )

    def create_categories(self):
        """Create furniture categories"""
        categories_data = [
            {
                'name': 'Sofas & Couches',
                'description': 'Comfortable seating for your living room',
                'slug': 'sofas-couches'
            },
            {
                'name': 'Tables',
                'description': 'Dining tables, coffee tables, and more',
                'slug': 'tables'
            },
            {
                'name': 'Chairs',
                'description': 'Dining chairs, office chairs, accent chairs',
                'slug': 'chairs'
            },
            {
                'name': 'Beds & Mattresses',
                'description': 'Comfortable sleeping solutions',
                'slug': 'beds-mattresses'
            },
            {
                'name': 'Storage & Organization',
                'description': 'Wardrobes, shelves, and storage solutions',
                'slug': 'storage-organization'
            },
            {
                'name': 'Lighting',
                'description': 'Lamps, chandeliers, and light fixtures',
                'slug': 'lighting'
            },
            {
                'name': 'Decor & Accessories',
                'description': 'Decorative items and home accessories',
                'slug': 'decor-accessories'
            }
        ]
        
        categories = []
        for cat_data in categories_data:
            category, created = Category.objects.get_or_create(
                slug=cat_data['slug'],
                defaults={
                    'name': cat_data['name'],
                    'description': cat_data['description'],
                    'is_active': True
                }
            )
            categories.append(category)
            if created:
                self.stdout.write(f'Created category: {category.name}')
        
        return categories

    def create_sample_users(self, count):
        """Create sample seller users"""
        sample_users = [
            {
                'username': 'furniture_expert',
                'email': 'expert@furniture.com',
                'first_name': 'John',
                'last_name': 'Smith',
                'is_seller': True
            },
            {
                'username': 'home_decor_pro',
                'email': 'pro@homedecor.com',
                'first_name': 'Sarah',
                'last_name': 'Johnson',
                'is_seller': True
            },
            {
                'username': 'modern_living',
                'email': 'modern@living.com',
                'first_name': 'Mike',
                'last_name': 'Chen',
                'is_seller': True
            },
            {
                'username': 'vintage_finds',
                'email': 'vintage@finds.com',
                'first_name': 'Emma',
                'last_name': 'Davis',
                'is_seller': True
            },
            {
                'username': 'luxury_interiors',
                'email': 'luxury@interiors.com',
                'first_name': 'David',
                'last_name': 'Wilson',
                'is_seller': True
            }
        ]
        
        users = []
        for i, user_data in enumerate(sample_users[:count]):
            user, created = User.objects.get_or_create(
                username=user_data['username'],
                defaults={
                    'email': user_data['email'],
                    'first_name': user_data['first_name'],
                    'last_name': user_data['last_name'],
                }
            )
            
            # Set seller attribute if the field exists
            if hasattr(user, 'is_seller'):
                user.is_seller = user_data['is_seller']
                user.save()
            
            users.append(user)
            if created:
                self.stdout.write(f'Created user: {user.username}')
        
        return users

    def create_sample_products(self, categories, sellers, count):
        """Create sample products with realistic data"""
        sample_products = [
            # Sofas & Couches
            {
                'name': 'Modern L-Shaped Sectional Sofa',
                'description': 'Spacious and comfortable L-shaped sectional perfect for modern living rooms. Features premium fabric upholstery and sturdy wooden frame.',
                'short_description': 'Modern L-shaped sectional with premium fabric',
                'category': 'sofas-couches',
                'price': Decimal('1299.99'),
                'original_price': Decimal('1599.99'),
                'stock_quantity': 15,
                'condition': 'new',
                'brand': 'ComfortLiving',
                'colors': ['Gray', 'Navy', 'Beige'],
                'materials': 'Fabric, Wood, Foam',
                'tags': ['sectional', 'modern', 'comfortable'],
                'weight': Decimal('85.5'),
                'dimensions_length': Decimal('240'),
                'dimensions_width': Decimal('160'),
                'dimensions_height': Decimal('85'),
                'is_featured': True,
                'image_url': 'https://images.unsplash.com/photo-1555041469-a586c61ea9bc?w=800'
            },
            {
                'name': 'Vintage Leather Chesterfield Sofa',
                'description': 'Classic Chesterfield sofa in genuine leather. Hand-crafted with traditional button tufting and rolled arms.',
                'short_description': 'Classic leather Chesterfield with button tufting',
                'category': 'sofas-couches',
                'price': Decimal('2199.99'),
                'stock_quantity': 8,
                'condition': 'new',
                'brand': 'Heritage Furniture',
                'colors': ['Brown', 'Black'],
                'materials': 'Genuine Leather, Hardwood',
                'tags': ['vintage', 'leather', 'chesterfield'],
                'weight': Decimal('75.0'),
                'dimensions_length': Decimal('200'),
                'dimensions_width': Decimal('90'),
                'dimensions_height': Decimal('80'),
                'is_featured': True,
                'image_url': 'https://images.unsplash.com/photo-1586023492125-27b2c045efd7?w=800'
            },
            
            # Tables
            {
                'name': 'Scandinavian Oak Dining Table',
                'description': 'Beautiful oak dining table with clean Scandinavian design. Seats 6-8 people comfortably.',
                'short_description': 'Scandinavian oak table for 6-8 people',
                'category': 'tables',
                'price': Decimal('899.99'),
                'original_price': Decimal('1099.99'),
                'stock_quantity': 12,
                'condition': 'new',
                'brand': 'Nordic Home',
                'colors': ['Natural Oak'],
                'materials': 'Solid Oak Wood',
                'tags': ['scandinavian', 'dining', 'oak'],
                'weight': Decimal('45.0'),
                'dimensions_length': Decimal('180'),
                'dimensions_width': Decimal('90'),
                'dimensions_height': Decimal('75'),
                'image_url': 'https://images.unsplash.com/photo-1449247709967-d4461a6a6103?w=800'
            },
            {
                'name': 'Industrial Metal Coffee Table',
                'description': 'Modern industrial coffee table with metal frame and reclaimed wood top. Perfect for contemporary living spaces.',
                'short_description': 'Industrial metal and wood coffee table',
                'category': 'tables',
                'price': Decimal('449.99'),
                'stock_quantity': 20,
                'condition': 'new',
                'brand': 'Urban Industrial',
                'colors': ['Black', 'Brown'],
                'materials': 'Metal, Reclaimed Wood',
                'tags': ['industrial', 'coffee table', 'modern'],
                'weight': Decimal('25.0'),
                'dimensions_length': Decimal('120'),
                'dimensions_width': Decimal('60'),
                'dimensions_height': Decimal('45'),
                'image_url': 'https://images.unsplash.com/photo-1549497538-303791108f95?w=800'
            },
            
            # Chairs
            {
                'name': 'Ergonomic Office Chair',
                'description': 'High-quality ergonomic office chair with lumbar support, adjustable height, and breathable mesh back.',
                'short_description': 'Ergonomic office chair with lumbar support',
                'category': 'chairs',
                'price': Decimal('299.99'),
                'stock_quantity': 25,
                'condition': 'new',
                'brand': 'ErgoComfort',
                'colors': ['Black', 'Gray'],
                'materials': 'Mesh, Plastic, Metal',
                'tags': ['office', 'ergonomic', 'adjustable'],
                'weight': Decimal('15.0'),
                'dimensions_length': Decimal('60'),
                'dimensions_width': Decimal('60'),
                'dimensions_height': Decimal('110'),
                'image_url': 'https://images.unsplash.com/photo-1541558869434-2840d308329a?w=800'
            },
            {
                'name': 'Mid-Century Accent Chair',
                'description': 'Stylish mid-century modern accent chair in velvet upholstery. Perfect for adding a pop of color to any room.',
                'short_description': 'Mid-century velvet accent chair',
                'category': 'chairs',
                'price': Decimal('399.99'),
                'stock_quantity': 18,
                'condition': 'new',
                'brand': 'Retro Style',
                'colors': ['Emerald', 'Mustard', 'Navy'],
                'materials': 'Velvet, Wood',
                'tags': ['mid-century', 'accent', 'velvet'],
                'weight': Decimal('18.0'),
                'dimensions_length': Decimal('70'),
                'dimensions_width': Decimal('65'),
                'dimensions_height': Decimal('85'),
                'is_featured': True,
                'image_url': 'https://images.unsplash.com/photo-1586023492125-27b2c045efd7?w=800'
            },
            
            # Additional products to reach the count
            {
                'name': 'Memory Foam Queen Mattress',
                'description': 'Premium memory foam mattress with cooling gel layer. Provides excellent support and temperature regulation.',
                'short_description': 'Queen memory foam mattress with cooling gel',
                'category': 'beds-mattresses',
                'price': Decimal('799.99'),
                'original_price': Decimal('999.99'),
                'stock_quantity': 10,
                'condition': 'new',
                'brand': 'SleepWell',
                'colors': ['White'],
                'materials': 'Memory Foam, Gel, Fabric',
                'tags': ['memory foam', 'cooling', 'queen'],
                'weight': Decimal('35.0'),
                'dimensions_length': Decimal('200'),
                'dimensions_width': Decimal('160'),
                'dimensions_height': Decimal('25'),
                'image_url': 'https://images.unsplash.com/photo-1515562141207-7a88fb7ce338?w=800'
            },
            {
                'name': 'Industrial Bookshelf Unit',
                'description': 'Five-tier industrial bookshelf with metal frame and wooden shelves. Great for storage and display.',
                'short_description': 'Five-tier industrial bookshelf',
                'category': 'storage-organization',
                'price': Decimal('249.99'),
                'stock_quantity': 22,
                'condition': 'new',
                'brand': 'Urban Storage',
                'colors': ['Black', 'Brown'],
                'materials': 'Metal, Wood',
                'tags': ['bookshelf', 'industrial', 'storage'],
                'weight': Decimal('28.0'),
                'dimensions_length': Decimal('80'),
                'dimensions_width': Decimal('35'),
                'dimensions_height': Decimal('180'),
                'image_url': 'https://images.unsplash.com/photo-1594224457193-09e515a8c2a3?w=800'
            },
            {
                'name': 'Modern Floor Lamp',
                'description': 'Sleek modern floor lamp with adjustable brightness and minimalist design. Perfect for reading corners.',
                'short_description': 'Modern adjustable floor lamp',
                'category': 'lighting',
                'price': Decimal('149.99'),
                'stock_quantity': 30,
                'condition': 'new',
                'brand': 'LightCraft',
                'colors': ['Black', 'White', 'Gold'],
                'materials': 'Metal, Fabric',
                'tags': ['floor lamp', 'modern', 'adjustable'],
                'weight': Decimal('8.5'),
                'dimensions_length': Decimal('40'),
                'dimensions_width': Decimal('40'),
                'dimensions_height': Decimal('150'),
                'image_url': 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=800'
            },
        ]
        
        # Create products up to the requested count
        import random
        created_count = 0
        
        for i in range(count):
            # Cycle through sample products or create variations
            base_product = sample_products[i % len(sample_products)]
            
            # Find category
            category = None
            for cat in categories:
                if cat.slug == base_product['category']:
                    category = cat
                    break
            
            if not category:
                category = categories[0]  # Fallback to first category
            
            # Select random seller
            seller = random.choice(sellers)
            
            # Create product name variation if needed
            product_name = base_product['name']
            if i >= len(sample_products):
                product_name = f"{base_product['name']} - Model {i + 1}"
            
            # Create the product
            product, created = Product.objects.get_or_create(
                name=product_name,
                seller=seller,
                defaults={
                    'description': base_product['description'],
                    'short_description': base_product['short_description'],
                    'category': category,
                    'price': base_product['price'],
                    'original_price': base_product.get('original_price'),
                    'stock_quantity': base_product['stock_quantity'],
                    'condition': base_product['condition'],
                    'brand': base_product['brand'],
                    'colors': base_product['colors'],
                    'materials': base_product['materials'],
                    'tags': base_product['tags'],
                    'weight': base_product.get('weight'),
                    'dimensions_length': base_product.get('dimensions_length'),
                    'dimensions_width': base_product.get('dimensions_width'),
                    'dimensions_height': base_product.get('dimensions_height'),
                    'is_featured': base_product.get('is_featured', False),
                    'is_active': True,
                }
            )
            
            if created:
                created_count += 1
                self.stdout.write(f'Created product: {product.name}')
                
                # Create product image if URL provided
                if 'image_url' in base_product:
                    try:
                        self.create_product_image(product, base_product['image_url'])
                    except Exception as e:
                        self.stdout.write(f'Warning: Could not download image for {product.name}: {e}')
        
        self.stdout.write(f'Created {created_count} new products')

    def create_product_image(self, product, image_url):
        """Download and create a product image"""
        try:
            response = requests.get(image_url, timeout=10)
            response.raise_for_status()
            
            # Create a temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
                temp_file.write(response.content)
                temp_file_path = temp_file.name
            
            # Create ProductImage
            with open(temp_file_path, 'rb') as image_file:
                image_content = image_file.read()
                
                product_image = ProductImage.objects.create(
                    product=product,
                    is_primary=True,
                    order=0
                )
                
                # Save the image file
                filename = f"{product.slug}_primary.jpg"
                product_image.image.save(
                    filename,
                    ContentFile(image_content),
                    save=True
                )
            
            # Clean up temp file
            os.unlink(temp_file_path)
            
        except Exception as e:
            raise Exception(f"Failed to download image: {e}")