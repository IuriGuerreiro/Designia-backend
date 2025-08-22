# S3 Storage Utility - Usage Examples

This document provides comprehensive examples for using the S3Storage utility in the Desginia marketplace backend.

## Configuration

Ensure your `.env` file contains the required S3 settings:

```bash
USE_S3=True
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_STORAGE_BUCKET_NAME=your_bucket_name
AWS_S3_REGION_NAME=us-east-1
```

## Basic Usage

### Import the S3 Storage Utility

```python
from utils.s3_storage import S3Storage, S3StorageError, get_s3_storage
# Or use the pre-configured instance
from utils import s3_storage
```

### Initialize S3Storage

```python
# Method 1: Use pre-configured instance (recommended)
storage = s3_storage

# Method 2: Create new instance
storage = S3Storage()

# Method 3: Get instance with validation
storage = get_s3_storage()
```

## File Upload Operations

### Upload a Django File Object

```python
from django.core.files.uploadedfile import InMemoryUploadedFile

def upload_product_image(request):
    try:
        image_file = request.FILES['image']
        
        # Upload with automatic key generation
        result = s3_storage.upload_file(
            file_obj=image_file,
            key=f"products/images/{image_file.name}",
            public=True,  # Make publicly accessible
            metadata={'uploaded_by': str(request.user.id)}
        )
        
        print(f"File uploaded successfully: {result['url']}")
        return result
        
    except S3StorageError as e:
        print(f"Upload failed: {str(e)}")
        return None
```

### Upload a Local File

```python
def upload_local_file():
    try:
        result = s3_storage.upload_file(
            file_obj="/path/to/local/file.jpg",
            key="uploads/local_file.jpg",
            public=False,
            metadata={'source': 'local_upload'}
        )
        
        return result['url']
        
    except S3StorageError as e:
        print(f"Upload failed: {str(e)}")
        return None
```

### Upload with Custom Content Type

```python
def upload_with_custom_type():
    try:
        with open('document.pdf', 'rb') as file:
            result = s3_storage.upload_file(
                file_obj=file,
                key="documents/important.pdf",
                content_type="application/pdf",
                metadata={'document_type': 'legal'}
            )
            
        return result
        
    except S3StorageError as e:
        print(f"Upload failed: {str(e)}")
        return None
```

## File Download Operations

### Download to Memory

```python
def download_file_content():
    try:
        content = s3_storage.download_file("products/images/sample.jpg")
        
        # Process the file content (bytes)
        with open('local_copy.jpg', 'wb') as f:
            f.write(content)
            
        return content
        
    except S3StorageError as e:
        print(f"Download failed: {str(e)}")
        return None
```

### Download to Local File

```python
def download_to_file():
    try:
        success = s3_storage.download_file(
            key="documents/report.pdf",
            download_path="/tmp/downloaded_report.pdf"
        )
        
        if success:
            print("File downloaded successfully")
            
        return success
        
    except S3StorageError as e:
        print(f"Download failed: {str(e)}")
        return False
```

## File Management Operations

### Check if File Exists

```python
def check_file_existence():
    exists = s3_storage.file_exists("products/images/product_123.jpg")
    
    if exists:
        print("File exists in S3")
    else:
        print("File not found")
        
    return exists
```

### Get File Information

```python
def get_file_details():
    try:
        info = s3_storage.get_file_info("products/images/product_123.jpg")
        
        print(f"File size: {info['size']} bytes")
        print(f"Content type: {info['content_type']}")
        print(f"Last modified: {info['last_modified']}")
        print(f"File URL: {info['url']}")
        
        return info
        
    except S3StorageError as e:
        print(f"Error getting file info: {str(e)}")
        return None
```

### Delete Files

```python
def delete_file():
    try:
        success = s3_storage.delete_file("products/images/old_product.jpg")
        
        if success:
            print("File deleted successfully")
            
        return success
        
    except S3StorageError as e:
        print(f"Delete failed: {str(e)}")
        return False
```

### List Files

```python
def list_product_images():
    try:
        result = s3_storage.list_files(
            prefix="products/images/",
            max_keys=50
        )
        
        print(f"Found {result['count']} files")
        
        for file in result['files']:
            print(f"- {file['key']} ({file['size']} bytes)")
            
        return result['files']
        
    except S3StorageError as e:
        print(f"Listing failed: {str(e)}")
        return []
```

## URL Generation

### Generate Public URLs

```python
def generate_public_url():
    url = s3_storage.get_file_url(
        key="products/images/public_product.jpg",
        public=True
    )
    
    print(f"Public URL: {url}")
    return url
```

### Generate Presigned URLs

```python
def generate_presigned_url():
    url = s3_storage.get_file_url(
        key="documents/private_doc.pdf",
        public=False,
        expires_in=3600  # 1 hour
    )
    
    print(f"Presigned URL (expires in 1 hour): {url}")
    return url
```

### Generate Presigned Upload URLs

```python
def generate_upload_url():
    try:
        result = s3_storage.generate_presigned_upload_url(
            key="uploads/new_file.jpg",
            expires_in=1800,  # 30 minutes
            content_type="image/jpeg",
            file_size_limit=5 * 1024 * 1024  # 5MB limit
        )
        
        print(f"Upload URL: {result['url']}")
        print(f"Form fields: {result['fields']}")
        
        return result
        
    except S3StorageError as e:
        print(f"Error generating upload URL: {str(e)}")
        return None
```

## Marketplace-Specific Methods

### Upload Product Images

```python
def upload_product_image_helper():
    # In a Django view
    try:
        image_file = request.FILES['product_image']
        product_id = "123e4567-e89b-12d3-a456-426614174000"
        
        result = s3_storage.upload_product_image(
            product_id=product_id,
            image_file=image_file,
            image_type='main'  # 'main', 'gallery', 'thumbnail'
        )
        
        # Save the URL to your product model
        product.image_url = result['url']
        product.save()
        
        return result
        
    except S3StorageError as e:
        print(f"Product image upload failed: {str(e)}")
        return None
```

### Upload User Avatars

```python
def upload_user_avatar():
    try:
        avatar_file = request.FILES['avatar']
        user_id = str(request.user.id)
        
        result = s3_storage.upload_user_avatar(
            user_id=user_id,
            avatar_file=avatar_file
        )
        
        # Update user profile
        request.user.profile.avatar_url = result['url']
        request.user.profile.save()
        
        return result
        
    except S3StorageError as e:
        print(f"Avatar upload failed: {str(e)}")
        return None
```

### Manage Product Images

```python
def manage_product_images():
    product_id = "123e4567-e89b-12d3-a456-426614174000"
    
    # List all images for a product
    images = s3_storage.list_product_images(product_id)
    print(f"Product has {len(images)} images")
    
    # Delete all product images (e.g., when product is deleted)
    deleted_count = s3_storage.delete_product_images(product_id)
    print(f"Deleted {deleted_count} images")
```

## Error Handling

### Comprehensive Error Handling

```python
from utils.s3_storage import S3StorageError

def safe_file_operation():
    try:
        # Attempt file operation
        result = s3_storage.upload_file(
            file_obj=file_object,
            key="test/file.jpg"
        )
        
        return {
            'success': True,
            'result': result
        }
        
    except S3StorageError as e:
        # Handle S3-specific errors
        return {
            'success': False,
            'error': str(e),
            'error_type': 'storage'
        }
        
    except Exception as e:
        # Handle unexpected errors
        return {
            'success': False,
            'error': str(e),
            'error_type': 'unexpected'
        }
```

## Django Integration Examples

### In Views

```python
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from utils import s3_storage

@csrf_exempt
def upload_product_image_view(request):
    if request.method == 'POST' and 'image' in request.FILES:
        try:
            image_file = request.FILES['image']
            product_id = request.POST.get('product_id')
            
            result = s3_storage.upload_product_image(
                product_id=product_id,
                image_file=image_file,
                image_type='gallery'
            )
            
            return JsonResponse({
                'success': True,
                'url': result['url'],
                'key': result['key']
            })
            
        except S3StorageError as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)
    
    return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)
```

### In Models

```python
from django.db import models
from utils import s3_storage

class Product(models.Model):
    name = models.CharField(max_length=200)
    image_url = models.URLField(blank=True)
    
    def upload_image(self, image_file):
        """Upload product image and update URL"""
        try:
            result = s3_storage.upload_product_image(
                product_id=str(self.id),
                image_file=image_file,
                image_type='main'
            )
            
            self.image_url = result['url']
            self.save()
            
            return result
            
        except S3StorageError as e:
            raise ValueError(f"Failed to upload image: {str(e)}")
    
    def delete_images(self):
        """Delete all product images from S3"""
        try:
            deleted_count = s3_storage.delete_product_images(str(self.id))
            return deleted_count
        except S3StorageError:
            return 0
```

## Performance Tips

1. **Use Public URLs for Public Content**: Set `public=True` for product images and other public content to avoid presigned URL generation overhead.

2. **Batch Operations**: When possible, batch multiple file operations to reduce API calls.

3. **Proper Error Handling**: Always wrap S3 operations in try-catch blocks.

4. **Content Type Detection**: Let the utility auto-detect content types or specify them explicitly for better performance.

5. **Metadata Usage**: Use metadata for tracking and organizing files efficiently.

6. **URL Caching**: Cache generated URLs when possible to reduce API calls.

## Security Considerations

1. **Private Content**: Use presigned URLs for private/sensitive content.

2. **Upload Validation**: Always validate file types and sizes before uploading.

3. **Access Control**: Use appropriate ACLs and bucket policies.

4. **Metadata Security**: Don't include sensitive information in metadata.

5. **URL Expiration**: Set appropriate expiration times for presigned URLs.