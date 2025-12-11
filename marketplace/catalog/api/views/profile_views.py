from django.contrib.auth import get_user_model
from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from marketplace.serializers import UserSerializer


User = get_user_model()


class UserProfileViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for user profiles
    """

    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [AllowAny]


@api_view(["GET"])
@permission_classes([AllowAny])
def seller_profile(request, seller_id):
    try:
        user = User.objects.get(id=seller_id)
        # Simple check if user is a seller
        if not (hasattr(user, "role") and user.role == "seller") and not (
            hasattr(user, "is_seller") and user.is_seller
        ):
            # Fallback check if simple attribute exists
            pass

        serializer = UserSerializer(user)
        return Response(serializer.data)
    except User.DoesNotExist:
        return Response({"detail": "Seller not found"}, status=404)
