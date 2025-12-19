from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import permissions, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from authentication.api.serializers import SellerApplicationSerializer
from authentication.api.serializers.response_serializers import (
    ErrorResponseSerializer,
    SellerApplicationAdminActionRequestSerializer,
    SellerApplicationAdminActionResponseSerializer,
    SellerApplicationStatusResponseSerializer,
    SellerApplicationSubmitResponseSerializer,
)
from authentication.domain.services.seller_service import SellerService
from authentication.infra.storage.s3_storage_provider import S3StorageProvider


def get_seller_service():
    return SellerService(storage_provider=S3StorageProvider())


class SellerApplicationCreateView(APIView):
    """POST only - Submit seller application"""

    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    http_method_names = ["post"]

    @extend_schema(
        operation_id="seller_application_submit",
        summary="Submit seller application",
        description="""
        Submit or resubmit application to become a seller.

        **Requirements:**
        - User must be authenticated
        - User must have 2FA enabled
        - User cannot already be a seller
        - Cannot have existing pending application

        **Files:** Upload 1-5 workshop photos (max 10MB each, jpg/png/webp)

        **Rate Limiting:** 2 applications per hour (if Kong Gateway enabled)
        """,
        request=SellerApplicationSerializer,
        responses={
            201: OpenApiResponse(
                response=SellerApplicationSubmitResponseSerializer,
                description="Application submitted successfully",
                examples=[
                    OpenApiExample(
                        "Successful Submission",
                        value={
                            "message": "Seller application submitted successfully",
                            "application_id": 42,
                            "images_uploaded": 3,
                        },
                    )
                ],
            ),
            400: OpenApiResponse(
                response=ErrorResponseSerializer, description="Validation error or requirements not met"
            ),
            403: OpenApiResponse(response=ErrorResponseSerializer, description="2FA not enabled or already a seller"),
        },
        tags=["Seller Applications"],
    )
    def post(self, request):
        # Extract images from request.FILES
        # The service expects a list of files for 'workshop_photos'
        # The serializer handles parsing, but here we might need manual extraction
        # because the Service method signature is specific:
        # submit_application(user, application_data, workshop_photos)

        # Extract data manually and let service handle business logic validation
        # Note: SellerApplicationSerializer has complex image handling
        # but we trust the service layer for validation

        application_data = {
            "business_name": request.data.get("business_name"),
            "seller_type": request.data.get("seller_type"),
            "motivation": request.data.get("motivation"),
            "portfolio_url": request.data.get("portfolio_url"),
            "social_media_url": request.data.get("social_media_url", ""),
        }

        # Get list of images. Frontend might send 'workshop_photos' or 'uploaded_images'
        workshop_photos = request.FILES.getlist("uploaded_images")

        service = get_seller_service()
        result = service.submit_application(request.user, application_data, workshop_photos)

        if result.success:
            return Response(result.data, status=status.HTTP_201_CREATED)

        return Response({"error": result.message}, status=status.HTTP_400_BAD_REQUEST)


class SellerApplicationStatusView(APIView):
    """GET only - Check seller application status"""

    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get"]

    @extend_schema(
        operation_id="seller_application_status",
        summary="Get seller application status",
        description="""
        Check the status of your seller application.

        **Possible Statuses:**
        - `none` - No application submitted
        - `pending` - Application under review
        - `approved` - Application approved (user is now seller)
        - `rejected` - Application rejected (can resubmit)
        """,
        responses={
            200: OpenApiResponse(
                response=SellerApplicationStatusResponseSerializer,
                description="Application status",
                examples=[
                    OpenApiExample(
                        "Pending Application",
                        value={
                            "has_application": True,
                            "is_seller": False,
                            "status": "pending",
                            "application_id": 42,
                            "submitted_at": "2025-01-15T10:30:00Z",
                            "admin_notes": None,
                            "rejection_reason": None,
                        },
                    ),
                    OpenApiExample(
                        "Approved Application",
                        value={
                            "has_application": True,
                            "is_seller": True,
                            "status": "approved",
                            "application_id": 42,
                            "submitted_at": "2025-01-15T10:30:00Z",
                            "admin_notes": "Great portfolio!",
                            "rejection_reason": None,
                        },
                    ),
                    OpenApiExample(
                        "Rejected Application",
                        value={
                            "has_application": True,
                            "is_seller": False,
                            "status": "rejected",
                            "application_id": 42,
                            "submitted_at": "2025-01-15T10:30:00Z",
                            "admin_notes": "Please improve portfolio quality",
                            "rejection_reason": "Portfolio does not meet quality standards",
                        },
                    ),
                ],
            )
        },
        tags=["Seller Applications"],
    )
    def get(self, request):
        """Get status of own application"""
        service = get_seller_service()
        status_data = service.get_application_status(request.user)
        return Response(status_data)


class SellerApplicationAdminView(APIView):
    """Admin view to approve/reject"""

    permission_classes = [permissions.IsAdminUser]

    @extend_schema(
        operation_id="seller_application_admin_action",
        summary="Approve or reject seller application (Admin only)",
        description="""
        Admin action to approve or reject a seller application.

        **Actions:**
        - `approve` - Approve application and upgrade user to seller role
        - `reject` - Reject application with reason (user can resubmit)

        **On Approval:**
        - User role changed to "seller"
        - User profile marked as verified seller
        - Email notification sent (if configured)

        **On Rejection:**
        - User can view rejection reason
        - User can resubmit improved application
        """,
        request=SellerApplicationAdminActionRequestSerializer,
        responses={
            200: OpenApiResponse(
                response=SellerApplicationAdminActionResponseSerializer,
                description="Action completed successfully",
                examples=[
                    OpenApiExample(
                        "Approval Success",
                        value={
                            "message": "Seller application approved",
                            "user_id": "123e4567-e89b-12d3-a456-426614174000",
                            "user_email": "seller@example.com",
                        },
                    ),
                    OpenApiExample(
                        "Rejection Success",
                        value={
                            "message": "Seller application rejected",
                            "user_id": "123e4567-e89b-12d3-a456-426614174000",
                            "user_email": "seller@example.com",
                        },
                    ),
                ],
            ),
            400: OpenApiResponse(
                response=ErrorResponseSerializer, description="Invalid action or application not found"
            ),
            403: OpenApiResponse(response=ErrorResponseSerializer, description="Not authorized (admin only)"),
        },
        tags=["Seller Applications (Admin)"],
    )
    def post(self, request, pk):
        action = request.data.get("action")  # approve, reject
        service = get_seller_service()

        if action == "approve":
            result = service.approve_application(pk, request.user)
        elif action == "reject":
            reason = request.data.get("reason", "")
            result = service.reject_application(pk, request.user, reason)
        else:
            return Response({"error": "Invalid action"}, status=status.HTTP_400_BAD_REQUEST)

        if result.success:
            return Response(result.data, status=status.HTTP_200_OK)

        return Response({"error": result.message}, status=status.HTTP_400_BAD_REQUEST)
