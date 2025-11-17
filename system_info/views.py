import logging

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseNotFound, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET
from packaging import version

from utils.s3_storage import S3StorageError, get_s3_storage

from .models import AppVersion

logger = logging.getLogger(__name__)

bucket_root_folders = ["furniture", "product-ar-models"]


@csrf_exempt
@require_GET
def s3_image_proxy(request, path):
    """
    Proxy endpoint to serve S3 images through the backend domain.
    This solves mixed content and CSP issues by serving images from the same domain.

    Usage: /api/system/s3-images/furniture/userId/productId/filename.jpg
    """
    try:
        # Validate S3 is enabled
        if not getattr(settings, "USE_S3", False):
            return HttpResponseBadRequest("S3 storage is not enabled")

        # Security: Validate path format to prevent directory traversal
        if not path or ".." in path or path.startswith("/"):
            return HttpResponseBadRequest("Invalid path")

        # Expected path format: furniture/userId/productId/filename
        path_parts = path.split("/")
        if len(path_parts) < 2 or path_parts[0] not in bucket_root_folders:
            return HttpResponseBadRequest("Invalid S3 path format")

        # Construct S3 key
        s3_key = path

        # Try to get from cache first (cache for 1 hour)
        cache_key = f"s3_proxy:{s3_key}"
        cached_response = cache.get(cache_key)
        if cached_response:
            return cached_response

        # Get S3 storage instance
        s3_storage = get_s3_storage()

        # Check if file exists in S3
        if not s3_storage.file_exists(s3_key):
            return HttpResponseNotFound("Image not found")

        # Get file from S3
        file_obj = s3_storage.get_file(s3_key)

        # Get file info for content type
        file_info = s3_storage.get_file_info(s3_key)
        content_type = file_info.get("content_type", "image/jpeg")

        # Create response with proper headers
        response = HttpResponse(file_obj["body"], content_type=content_type)

        # Add caching headers
        response["Cache-Control"] = "public, max-age=3600"  # Cache for 1 hour
        response["Access-Control-Allow-Origin"] = "*"  # Allow CORS for images

        # Cache the response
        cache.set(cache_key, response, 3600)  # Cache for 1 hour

        logger.debug(f"Served S3 image via proxy: {s3_key}")
        return response

    except S3StorageError as e:
        logger.error(f"S3 storage error for path {path}: {str(e)}")
        return HttpResponseNotFound("Image not found")
    except Exception as e:
        logger.error(f"Unexpected error in S3 proxy for path {path}: {str(e)}")
        return HttpResponseBadRequest("Server error")


@csrf_exempt
@require_GET
def s3_image_info(request, path):
    """
    Get metadata about an S3 image without serving the actual image.
    Useful for frontend to check image existence and get metadata.

    Usage: /api/system/s3-images/furniture/userId/productId/filename.jpg/info/
    """
    try:
        # Validate S3 is enabled
        if not getattr(settings, "USE_S3", False):
            return HttpResponseBadRequest("S3 storage is not enabled")

        # Security: Validate path format
        if not path or ".." in path or path.startswith("/"):
            return HttpResponseBadRequest("Invalid path")

        # Expected path format: furniture/userId/productId/filename
        path_parts = path.split("/")
        if len(path_parts) < 4 or path_parts[0] != "furniture":
            return HttpResponseBadRequest("Invalid S3 path format")

        # Construct S3 key
        s3_key = path

        # Get S3 storage instance
        s3_storage = get_s3_storage()

        # Check if file exists and get info
        if not s3_storage.file_exists(s3_key):
            return HttpResponseNotFound("Image not found")

        file_info = s3_storage.get_file_info(s3_key)

        # Return JSON response with file metadata
        import json

        return HttpResponse(
            json.dumps(
                {
                    "exists": True,
                    "key": file_info["key"],
                    "size": file_info["size"],
                    "last_modified": (
                        file_info["last_modified"].isoformat() if file_info.get("last_modified") else None
                    ),
                    "content_type": file_info.get("content_type", "image/jpeg"),
                    "proxy_url": f"/api/system/s3-images/{path}",
                }
            ),
            content_type="application/json",
        )

    except S3StorageError as e:
        logger.error(f"S3 storage error for image info {path}: {str(e)}")
        return HttpResponseNotFound("Image not found")
    except Exception as e:
        logger.error(f"Unexpected error in S3 image info for path {path}: {str(e)}")
        return HttpResponseBadRequest("Server error")


@csrf_exempt
@require_GET
def app_version_check(request):
    """
    Check if the app version meets mandatory requirements.

    Query parameters:
    - platform: 'android' or 'ios'
    - current_version: current app version (e.g., '1.1.0')

    Returns:
    - requires_update: boolean
    - is_mandatory: boolean
    - latest_version: string
    - update_message: string
    - download_url: string
    """
    try:
        platform = request.GET.get("platform")
        current_version = request.GET.get("current_version")

        if not platform or not current_version:
            return JsonResponse({"error": "platform and current_version parameters are required"}, status=400)

        if platform not in ["android", "ios"]:
            return JsonResponse({"error": "Invalid platform. Must be android or ios"}, status=400)

        # Get version info from database
        try:
            app_version = AppVersion.objects.get(platform=platform, is_active=True)
        except AppVersion.DoesNotExist:
            # No version requirements set
            return JsonResponse(
                {
                    "requires_update": False,
                    "is_mandatory": False,
                    "latest_version": current_version,
                    "update_message": "",
                    "download_url": "",
                }
            )

        # Compare versions
        try:
            current = version.parse(current_version)
            mandatory = version.parse(app_version.mandatory_version)
            latest = version.parse(app_version.latest_version)

            requires_update = current < latest
            is_mandatory = current < mandatory

        except Exception as e:
            logger.error(f"Version parsing error: {e}")
            return JsonResponse({"error": "Invalid version format"}, status=400)

        return JsonResponse(
            {
                "requires_update": requires_update,
                "is_mandatory": is_mandatory,
                "latest_version": app_version.latest_version,
                "update_message": app_version.update_message,
                "download_url": app_version.download_url,
            }
        )

    except Exception as e:
        logger.error(f"Error in app version check: {e}")
        return JsonResponse({"error": "Internal server error"}, status=500)
