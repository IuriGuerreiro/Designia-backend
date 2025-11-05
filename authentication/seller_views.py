from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone

from .seller_models import SellerApplication, SellerApplicationImage
from .seller_serializers import (
    SellerApplicationSerializer,
    SellerApplicationAdminSerializer,
    UserRoleSerializer
)
from .models import CustomUser
from utils.rbac import is_admin
import logging

logger = logging.getLogger(__name__)


class SellerApplicationCreateView(generics.CreateAPIView):
    """Create a new seller application"""
    serializer_class = SellerApplicationSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def perform_create(self, serializer):
        # Check if user already has an application
        if hasattr(self.request.user, 'seller_application'):
            raise serializers.ValidationError(
                "You already have a seller application submitted."
            )

        serializer.save(user=self.request.user)

    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class SellerApplicationDetailView(generics.RetrieveAPIView):
    """Get seller application details"""
    serializer_class = SellerApplicationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return get_object_or_404(SellerApplication, user=self.request.user)


class SellerApplicationListView(generics.ListAPIView):
    """List all seller applications (admin only)"""
    serializer_class = SellerApplicationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request, *args, **kwargs):
        # Check if user has admin privileges
        if not is_admin(request.user):
            return Response(
                {'error': 'Permission denied. Admin access required.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        user = self.request.user

        # Only admin/superuser can see all applications
        if not is_admin(user):
            return SellerApplication.objects.none()

        # Filter by status if provided
        status_filter = self.request.query_params.get('status')
        queryset = SellerApplication.objects.all()

        if status_filter:
            queryset = queryset.filter(status=status_filter)
            logger.info(f"Filtered queryset by status: {status_filter}")

        return queryset.order_by('-submitted_at')


class SellerApplicationAdminUpdateView(generics.UpdateAPIView):
    """Admin actions on seller applications"""
    serializer_class = SellerApplicationAdminSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        # Only admin/superuser can update applications
        from utils.rbac import is_admin
        if not is_admin(user):
            return SellerApplication.objects.none()

        return SellerApplication.objects.all()


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def seller_application_status(request):
    """Get current user's most recent seller application status"""
    application = (
        SellerApplication.objects.filter(user=request.user)
        .order_by('-submitted_at')
        .first()
    )

    if application:
        return Response({
            'has_application': True,
            'is_seller': is_admin(request.user) or getattr(request.user, 'role', None) == 'seller',
            'status': application.status,
            'application_id': application.id,
            'submitted_at': application.submitted_at,
            'admin_notes': application.admin_notes,
            'rejection_reason': application.rejection_reason,
        })

    return Response({
        'has_application': False,
        'is_seller': is_admin(request.user) or getattr(request.user, 'role', None) == 'seller',
        'status': None
    })


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def apply_to_become_seller(request):
    """Apply to become a seller - handles form data from BecomeSellerForm"""
    import logging
    logger = logging.getLogger(__name__)

    logger.info("=== SELLER APPLICATION DEBUG START ===")
    logger.info(f"User: {request.user.id} ({request.user.email})")
    logger.info(f"User role: {getattr(request.user, 'role', 'NO_ROLE_ATTR')}")
    logger.info(f"Request method: {request.method}")
    logger.info(f"Content type: {request.content_type}")
    logger.info(f"Request data keys: {list(request.data.keys()) if hasattr(request, 'data') else 'NO_DATA'}")
    logger.info(f"Request FILES keys: {list(request.FILES.keys()) if hasattr(request, 'FILES') else 'NO_FILES'}")

    # Test imports and model access
    logger.info("Step 0: Testing model imports...")
    try:
        logger.info(f"SellerApplication model: {SellerApplication}")
        logger.info(f"SellerApplicationImage model: {SellerApplicationImage}")
        logger.info(f"SellerApplicationSerializer: {SellerApplicationSerializer}")
        logger.info("[OK] All imports working")
    except Exception as import_error:
        logger.error(f"Import error: {import_error}")
        return Response({'error': f'Import error: {str(import_error)}'}, status=500)

    try:
        # Check existing applications and in-progress constraints
        logger.info("Step 1: Checking for existing application(s)...")
        existing = (
            SellerApplication.objects.filter(user=request.user)
            .order_by('-submitted_at')
            .first()
        )

        if existing and existing.status in ['pending', 'under_review', 'revision_requested']:
            logger.warning("User already has an in-progress application")
            return Response(
                {'error': 'You already have a seller application in progress.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        logger.info("✓ No in-progress application found; proceeding")

        # Check if user is already a seller
        logger.info("Step 2: Checking if user is already a seller...")
        if getattr(request.user, 'role', None) == 'seller':
            logger.warning("User is already a seller")
            return Response(
                {'error': 'You are already a verified seller.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        logger.info("✓ User is not already a seller")

        # Check if user has 2FA enabled
        logger.info("Step 2.5: Checking if user has 2FA enabled...")
        if not request.user.two_factor_enabled:
            logger.warning("User does not have 2FA enabled")
            return Response(
                {'error': 'Two-factor authentication (2FA) must be enabled before applying to become a seller. Please enable 2FA in your settings.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        logger.info("✓ User has 2FA enabled")

        logger.info("Step 3: Starting transaction...")
        with transaction.atomic():
            logger.info("Step 4: Extracting form data...")

            # Create application
            application_data = {
                'business_name': request.data.get('businessName'),
                'seller_type': request.data.get('sellerType'),
                'motivation': request.data.get('motivation'),
                'portfolio_url': request.data.get('portfolio'),
                'social_media_url': request.data.get('socialMedia', ''),
                'user': request.user.id  # Pass user ID, not user object
            }

            logger.info(f"Application data: {application_data}")
            logger.info("Step 5: Creating serializer...")

            # If there is a previous rejected application, update and resubmit it
            if existing and existing.status == 'rejected':
                logger.info("Step 6: Resubmitting previously rejected application...")
                # Update fields
                existing.business_name = application_data.get('business_name')
                existing.seller_type = application_data.get('seller_type')
                existing.motivation = application_data.get('motivation')
                existing.portfolio_url = application_data.get('portfolio_url')
                existing.social_media_url = application_data.get('social_media_url', '')
                existing.status = 'pending'
                existing.admin_notes = ''
                existing.rejection_reason = ''
                existing.reviewed_at = None
                existing.approved_by = None
                existing.rejected_by = None
                existing.submitted_at = timezone.now()
                existing.save()

                # Replace images
                existing.images.all().delete()
                workshop_files = request.FILES.getlist('workshopPhotos')
                logger.info(f"Found {len(workshop_files)} workshop files for resubmission")
                for index, image_file in enumerate(workshop_files):
                    SellerApplicationImage.objects.create(
                        application=existing,
                        image=image_file,
                        image_type='workshop',
                        description=f'Workshop photo {index + 1}',
                        order=index
                    )

                logger.info("=== SELLER APPLICATION RESUBMIT SUCCESS ===")
                return Response({
                    'success': True,
                    'message': 'Seller application resubmitted successfully!',
                    'application_id': existing.id
                }, status=status.HTTP_200_OK)

            # No previous application: create a new one
            serializer = SellerApplicationSerializer(data=application_data)
            logger.info("Step 6: Validating serializer...")

            if not serializer.is_valid():
                logger.error(f"Serializer validation failed: {serializer.errors}")
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            logger.info("✓ Serializer is valid")
            logger.info("Step 7: Saving application...")
            application = serializer.save()
            logger.info(f"✓ Application saved with ID: {application.id}")

            # Handle workshop images
            logger.info("Step 8: Processing workshop images...")
            workshop_files = request.FILES.getlist('workshopPhotos')
            logger.info(f"Found {len(workshop_files)} workshop files")

            for index, image_file in enumerate(workshop_files):
                logger.info(f"Processing image {index + 1}: {image_file.name}")
                SellerApplicationImage.objects.create(
                    application=application,
                    image=image_file,
                    image_type='workshop',
                    description=f'Workshop photo {index + 1}',
                    order=index
                )
                logger.info(f"✓ Image {index + 1} saved")

            logger.info("=== SELLER APPLICATION SUCCESS ===")
            return Response({
                'success': True,
                'message': 'Seller application submitted successfully!',
                'application_id': application.id
            }, status=status.HTTP_201_CREATED)

    except Exception as e:
        logger.error(f"=== SELLER APPLICATION ERROR ===")
        logger.error(f"Exception type: {type(e).__name__}")
        logger.error(f"Exception message: {str(e)}")
        logger.error(f"Exception args: {e.args}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")

        return Response(
            {'error': f'Failed to submit application: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def user_role_info(request):
    """Get current user's role information"""
    serializer = UserRoleSerializer(request.user)
    return Response({
        **serializer.data,
        'is_seller': is_admin(request.user) or getattr(request.user, 'role', None) == 'seller',
        'is_admin': is_admin(request.user),
        'can_sell_products': request.user.can_sell_products()
    })


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def admin_approve_seller(request, application_id):
    """Admin endpoint to approve seller application"""
    if not is_admin(request.user):
        return Response(
            {'error': 'Permission denied. Admin access required.'},
            status=status.HTTP_403_FORBIDDEN
        )

    try:
        application = SellerApplication.objects.get(id=application_id)
        application.approve_application(request.user)

        return Response({
            'success': True,
            'message': f'Seller application approved for {application.user.email}'
        })
    except SellerApplication.DoesNotExist:
        return Response(
            {'error': 'Application not found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def admin_reject_seller(request, application_id):
    """Admin endpoint to reject seller application"""
    if not is_admin(request.user):
        return Response(
            {'error': 'Permission denied. Admin access required.'},
            status=status.HTTP_403_FORBIDDEN
        )

    try:
        application = SellerApplication.objects.get(id=application_id)
        reason = request.data.get('reason', 'Application rejected by admin')
        application.reject_application(request.user, reason)

        return Response({
            'success': True,
            'message': f'Seller application rejected for {application.user.email}'
        })
    except SellerApplication.DoesNotExist:
        return Response(
            {'error': 'Application not found'},
            status=status.HTTP_404_NOT_FOUND
        )
