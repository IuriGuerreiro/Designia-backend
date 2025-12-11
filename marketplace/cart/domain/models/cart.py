from django.contrib.auth import get_user_model
from django.db import models

from marketplace.catalog.domain.models.catalog import Product


User = get_user_model()


class Cart(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="cart")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Shopping Cart"
        verbose_name_plural = "Shopping Carts"
        app_label = "marketplace"

    @classmethod
    def get_or_create_cart(cls, user):
        """Get existing cart or create a new one for the user."""
        cart, _ = cls.objects.get_or_create(user=user)
        return cart

    def __str__(self):
        return f"Cart for {self.user.username}"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["cart", "product"]
        app_label = "marketplace"

    @property
    def total_price(self):
        return self.quantity * self.product.price

    def __str__(self):
        return f"{self.quantity}x {self.product.name} in {self.cart.user.username}'s cart"
