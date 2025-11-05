from rest_framework import permissions

from utils.rbac import is_admin, is_seller


class IsSellerOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow sellers of a product to edit it.
    """

    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed for any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions are only allowed to the seller of the product.
        return obj.seller == request.user


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it.
    """

    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed for any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions are only allowed to the owner of the object.
        # For ProductReview, check if the reviewer is the current user
        if hasattr(obj, "reviewer"):
            return obj.reviewer == request.user

        # For ProductImage, check if the product seller is the current user
        if hasattr(obj, "product"):
            return obj.product.seller == request.user

        # For other objects with user field
        if hasattr(obj, "user"):
            return obj.user == request.user

        # For objects with seller field
        if hasattr(obj, "seller"):
            return obj.seller == request.user

        return False


class IsSellerOrBuyerOrReadOnly(permissions.BasePermission):
    """
    Custom permission for orders - allows sellers and buyers to view/edit their orders
    """

    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed for any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in permissions.SAFE_METHODS:
            # Allow if user is the buyer or one of the sellers
            if obj.buyer == request.user:
                return True

            # Check if user is a seller in any of the order items
            if obj.items.filter(seller=request.user).exists():
                return True

            # Allow staff to view all orders
            if request.user.is_staff:
                return True

            return False

        # Write permissions
        # Buyers can update their orders (limited fields)
        if obj.buyer == request.user:
            return True

        # Sellers can update order status for their items
        if obj.items.filter(seller=request.user).exists():
            return True

        # Staff can update any order
        if request.user.is_staff:
            return True

        return False


class IsCartOwner(permissions.BasePermission):
    """
    Custom permission to only allow cart owner to access their cart
    """

    def has_object_permission(self, request, view, obj):
        # Check if the cart belongs to the current user
        if hasattr(obj, "user"):
            return obj.user == request.user

        # For cart items, check if the cart belongs to the current user
        if hasattr(obj, "cart"):
            return obj.cart.user == request.user

        return False


class IsReviewerOrReadOnly(permissions.BasePermission):
    """
    Custom permission for product reviews
    """

    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed for any request
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions are only allowed to the reviewer
        return obj.reviewer == request.user


class IsProductOwner(permissions.BasePermission):
    """
    Custom permission to check if user owns the product
    """

    def has_permission(self, request, view):
        # Allow all authenticated users for safe methods
        if request.method in permissions.SAFE_METHODS:
            return request.user.is_authenticated

        # For write operations, need to check object-level permission
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # For product-related objects, check if user owns the product
        if hasattr(obj, "product"):
            return obj.product.seller == request.user

        # For direct product access
        if hasattr(obj, "seller"):
            return obj.seller == request.user

        return False


class IsSellerUser(permissions.BasePermission):
    """
    Permission to check if user has seller role
    Allows sellers and admins to access seller-only endpoints
    """

    def has_permission(self, request, view):
        # User must be authenticated
        if not request.user.is_authenticated:
            return False

        # Check if user is seller or admin
        return is_seller(request.user)


class IsAdminUser(permissions.BasePermission):
    """
    Permission to check if user has admin role
    Only allows admins to access admin-only endpoints
    """

    def has_permission(self, request, view):
        # User must be authenticated
        if not request.user.is_authenticated:
            return False

        # Check if user is admin
        return is_admin(request.user)
