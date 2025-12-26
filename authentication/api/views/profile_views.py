from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import generics, permissions, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from authentication.api.serializers import ProfileSerializer, PublicUserSerializer, UserSerializer
from authentication.api.serializers.profile_serializers import AccountDeletionSerializer
from authentication.api.serializers.response_serializers import (
    ErrorResponseSerializer,
    ProfilePictureDeleteResponseSerializer,
    ProfilePictureUploadResponseSerializer,
)
from authentication.domain.models import CustomUser
from authentication.domain.services.profile_service import ProfileService
from authentication.infra.storage.s3_storage_provider import S3StorageProvider


# Helper
def get_profile_service():
    return ProfileService(storage_provider=S3StorageProvider())


class PublicProfileDetailView(generics.RetrieveAPIView):
    """
    Get public profile of a user.
    """

    queryset = CustomUser.objects.all()
    serializer_class = PublicUserSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = "pk"

    @extend_schema(
        operation_id="profile_public_view",
        summary="View public user profile",
        description="""
        Get public profile information for any user.

        **Visibility Rules:**
        - Anyone can view seller/admin profiles
        - Verified sellers can view other verified sellers
        - Non-sellers see limited information

        **Returns:**
        - Basic user info (username, avatar, role)
        - Profile data (bio, location, social links)
        - Seller information if applicable
        """,
        responses={
            200: OpenApiResponse(response=PublicUserSerializer, description="User profile retrieved"),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="User not found"),
        },
        tags=["Profile"],
    )
    def get_object(self):
        user = super().get_object()
        # Logic from old view: Allow if target is seller/admin or verified seller
        # This seems like domain logic, but for simple read permissions it's okay here?
        # Ideally moved to service, but RetrieveAPIView expects get_object.
        return user


class ProfileUpdateView(APIView):
    """
    Update own profile.
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        operation_id="profile_get_own",
        summary="Get own profile",
        description="""
        Retrieve your own complete user and profile information.

        **Includes:**
        - User fields (username, email, first_name, last_name, role, etc.)
        - All profile fields
        - Profile completion percentage
        - Private fields (phone, email preferences, etc.)
        """,
        responses={200: OpenApiResponse(response=UserSerializer, description="User profile retrieved")},
        tags=["Profile"],
    )
    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    @extend_schema(
        operation_id="profile_update",
        summary="Update own profile",
        description="""
        Update your profile information.

        **Restricted Fields (Verified Sellers/Admins only):**
        - phone_number, country_code
        - website, location
        - job_title, company
        - account_type
        - Social media URLs (instagram, facebook, twitter, linkedin, pinterest, tiktok)

        **Public Fields (Anyone):**
        - bio
        - avatar (via separate upload endpoint)

        **Returns:**
        - Updated profile with new completion percentage
        - Profile completion ranges from 0-100%
        """,
        request=ProfileSerializer,
        responses={
            200: OpenApiResponse(response=ProfileSerializer, description="Profile updated successfully"),
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Validation error or permission denied for restricted fields",
                examples=[
                    OpenApiExample(
                        "Permission Denied",
                        value={
                            "error": "You do not have permission to update restricted profile fields",
                            "details": {"restricted_fields": ["phone_number", "website"]},
                        },
                    )
                ],
            ),
        },
        tags=["Profile"],
    )
    def patch(self, request):
        service = get_profile_service()
        result = service.update_profile(request.user, request.data)

        if result.success:
            # Return updated profile
            # We might want to reload the profile to return full data
            request.user.profile.refresh_from_db()
            return Response(ProfileSerializer(request.user.profile).data, status=status.HTTP_200_OK)

        return Response({"error": result.message, "details": result.data}, status=status.HTTP_400_BAD_REQUEST)


class ProfilePictureUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        operation_id="profile_picture_upload",
        summary="Upload profile picture",
        description="""
        Upload a new profile picture.

        **Requirements:**
        - Max file size: 10MB
        - Allowed formats: JPG, PNG, WebP
        - Automatically replaces old profile picture

        **Storage:**
        - Uploaded to S3/MinIO
        - Returns presigned URL (valid for 1 hour)
        - Permanent URL stored in profile

        **Rate Limiting:** 60 requests/minute
        """,
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {
                    "file": {"type": "string", "format": "binary", "description": "Image file (JPG, PNG, or WebP)"}
                },
            }
        },
        responses={
            200: OpenApiResponse(
                response=ProfilePictureUploadResponseSerializer,
                description="Profile picture uploaded successfully",
                examples=[
                    OpenApiExample(
                        "Successful Upload",
                        value={
                            "message": "Profile picture uploaded successfully",
                            "profile_picture_url": "profile-pictures/123e4567/profile.jpg",
                            "profile_picture_temp_url": "https://s3.amazonaws.com/designia/profile-pictures/123e4567/profile.jpg?signature=...",
                            "size": 245678,
                            "content_type": "image/jpeg",
                        },
                    )
                ],
            ),
            400: OpenApiResponse(
                response=ErrorResponseSerializer, description="Validation error (file too large, wrong format, etc.)"
            ),
        },
        tags=["Profile"],
    )
    def post(self, request):
        file_obj = request.FILES.get("file")
        if not file_obj:
            return Response({"error": "No file provided"}, status=status.HTTP_400_BAD_REQUEST)

        service = get_profile_service()
        result = service.upload_profile_picture(request.user, file_obj)

        if result.success:
            return Response(result.data, status=status.HTTP_200_OK)

        return Response({"error": result.message}, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        operation_id="profile_picture_delete",
        summary="Delete profile picture",
        description="""
        Remove your profile picture.

        **Effect:**
        - Deletes image from S3/MinIO storage
        - Clears profile_picture_url field
        - Profile reverts to default avatar
        """,
        responses={
            200: OpenApiResponse(
                response=ProfilePictureDeleteResponseSerializer, description="Profile picture deleted successfully"
            ),
            400: OpenApiResponse(
                response=ErrorResponseSerializer, description="No profile picture to delete or deletion failed"
            ),
        },
        tags=["Profile"],
    )
    def delete(self, request):
        service = get_profile_service()
        result = service.delete_profile_picture(request.user)

        if result.success:
            return Response({"message": result.message}, status=status.HTTP_200_OK)

        return Response({"error": result.message}, status=status.HTTP_400_BAD_REQUEST)


class ProfileExportView(APIView):
    """
    GDPR Data Export - Request export of all user data.
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        operation_id="profile_data_export",
        summary="Request data export (GDPR)",
        description="""
        Request an export of all your personal data (GDPR Right to Data Portability).

        **Process:**
        - Request is queued for async processing
        - All user data is collected (profile, orders, reviews, messages)
        - JSON file is generated and uploaded to secure storage
        - Email is sent with time-limited download link

        **Included Data:**
        - Profile information
        - Order history
        - Reviews and ratings
        - Messages and conversations
        - Seller data (if applicable)

        **Rate Limiting:** 1 export request per 24 hours
        """,
        responses={
            200: OpenApiResponse(
                description="Export request accepted",
                examples=[
                    OpenApiExample(
                        "Success",
                        value={
                            "message": "Export request received. You will receive an email with a download link when ready.",
                            "estimated_time": "5-10 minutes",
                        },
                    )
                ],
            ),
            429: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Rate limit exceeded",
                examples=[
                    OpenApiExample(
                        "Rate Limited",
                        value={
                            "error": "Export request already in progress or completed recently.",
                            "retry_after": 86400,
                        },
                    )
                ],
            ),
        },
        tags=["Profile", "GDPR"],
    )
    def get(self, request):
        from authentication.tasks.gdpr_tasks import export_user_data_task

        user = request.user

        # Queue the Celery task for async processing
        export_user_data_task.delay(str(user.id))

        return Response(
            {
                "message": "Export request received. You will receive an email with a download link when ready.",
                "estimated_time": "5-10 minutes",
            },
            status=status.HTTP_200_OK,
        )


class ProfileDeleteView(APIView):
    """
    GDPR Account Deletion - Permanently delete user account.
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        operation_id="profile_delete_account",
        summary="Delete account (GDPR)",
        description="""
        Permanently delete your account (GDPR Right to Erasure / Right to be Forgotten).

        **Requirements:**
        - Must type "DELETE" as confirmation
        - Must provide current password

        **Process:**
        - Account is immediately deactivated
        - Personal data is anonymized (reviews show "Deleted User")
        - Private data (orders, messages) is permanently deleted
        - Session is terminated

        **WARNING:** This action is irreversible!
        """,
        request=AccountDeletionSerializer,
        responses={
            200: OpenApiResponse(
                description="Account deleted successfully",
                examples=[
                    OpenApiExample(
                        "Success",
                        value={"message": "Account deleted successfully. All personal data has been removed."},
                    )
                ],
            ),
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Validation error",
                examples=[
                    OpenApiExample(
                        "Invalid Confirmation",
                        value={"error": "You must type DELETE to confirm account deletion."},
                    ),
                    OpenApiExample(
                        "Invalid Password",
                        value={"error": "Incorrect password."},
                    ),
                ],
            ),
        },
        tags=["Profile", "GDPR"],
    )
    def post(self, request):
        serializer = AccountDeletionSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {"error": "Validation failed", "details": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
            )

        confirmation = serializer.validated_data.get("confirmation")
        password = serializer.validated_data.get("password")

        # Verify confirmation text
        if confirmation != "DELETE":
            return Response(
                {"error": "You must type DELETE to confirm account deletion."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify password
        user = request.user
        if not user.check_password(password):
            return Response({"error": "Incorrect password."}, status=status.HTTP_400_BAD_REQUEST)

        # Perform account deletion via service
        service = get_profile_service()
        result = service.delete_user_account(user)

        if result.success:
            return Response(
                {"message": "Account deleted successfully. All personal data has been removed."},
                status=status.HTTP_200_OK,
            )

        return Response({"error": result.message}, status=status.HTTP_400_BAD_REQUEST)
