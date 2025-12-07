import random
import uuid
from decimal import Decimal

import factory
from django.contrib.auth import get_user_model
from django.utils.text import slugify  # Import slugify
from faker import Faker  # Import Faker class for explicit generation

from ar.models import ProductARModel
from marketplace.models import (
    Cart,
    CartItem,
    Category,
    Order,
    OrderItem,
    Product,
    ProductFavorite,
    ProductImage,
    ProductReview,
)
from payment_system.models import ExchangeRate, PaymentTracker, PaymentTransaction, Payout, PayoutItem

User = get_user_model()
fake = Faker()  # Instantiate Faker once


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    id = factory.LazyFunction(uuid.uuid4)
    username = factory.Sequence(lambda n: f"user_{n}")
    email = factory.Sequence(lambda n: f"user_{n}@example.com")
    password = factory.PostGenerationMethodCall("set_password", "defaultpassword")
    is_active = True
    is_email_verified = True
    role = "user"


class SellerFactory(UserFactory):
    role = "seller"
    username = factory.Sequence(lambda n: f"seller_{n}")
    email = factory.Sequence(lambda n: f"seller_{n}@example.com")


class AdminFactory(UserFactory):
    role = "admin"
    is_superuser = True
    is_staff = True
    username = factory.Sequence(lambda n: f"admin_{n}")
    email = factory.Sequence(lambda n: f"admin_{n}@example.com")


class CategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Category

    name = factory.Sequence(lambda n: f"Category {n}")
    slug = factory.LazyAttribute(lambda o: slugify(o.name))
    description = factory.Faker("text", max_nb_chars=200)
    is_active = True


class ProductFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Product

    id = factory.LazyFunction(uuid.uuid4)
    name = factory.Sequence(lambda n: f"Product {n}")
    slug = factory.LazyAttribute(lambda o: slugify(o.name))
    description = factory.Faker("paragraph", nb_sentences=5)
    short_description = factory.Faker("sentence", nb_words=10)
    price = factory.LazyFunction(lambda: Decimal(f"{random.randint(10, 500)}.00"))
    stock_quantity = factory.Faker("random_int", min=0, max=100)
    condition = factory.Iterator([choice[0] for choice in Product.CONDITION_CHOICES])
    brand = factory.Faker("company")
    is_active = True
    is_featured = False
    is_digital = False

    seller = factory.SubFactory(SellerFactory)
    category = factory.SubFactory(CategoryFactory)

    @factory.post_generation
    def set_original_price(self, create, extracted, **kwargs):
        if create and extracted is not None:
            if extracted is True:  # If extracted is True, set a higher original price
                self.original_price = self.price + Decimal(f"{random.randint(10, 50)}.00")
            elif isinstance(extracted, Decimal):  # If a Decimal is provided
                self.original_price = extracted
            else:  # No sale
                self.original_price = None
            self.save()


class ProductOnSaleFactory(ProductFactory):
    @factory.post_generation
    def set_on_sale(self, create, extracted, **kwargs):
        if create:
            self.original_price = self.price + Decimal(f"{random.randint(10, 50)}.00")
            self.save()


class ProductOutOfStockFactory(ProductFactory):
    stock_quantity = 0


class ProductImageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProductImage

    product = factory.SubFactory(ProductFactory)
    image = factory.django.ImageField(filename="test_image.jpg")
    alt_text = factory.Faker("sentence", nb_words=5)
    is_primary = False
    order = 0


class ProductReviewFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProductReview

    product = factory.SubFactory(ProductFactory)
    reviewer = factory.SubFactory(UserFactory)
    rating = factory.Faker("random_int", min=1, max=5)
    title = factory.Faker("sentence", nb_words=5)
    comment = factory.Faker("paragraph", nb_sentences=2)
    is_verified_purchase = True
    is_active = True


class ProductFavoriteFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProductFavorite

    user = factory.SubFactory(UserFactory)
    product = factory.SubFactory(ProductFactory)


class ProductARModelFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProductARModel

    product = factory.SubFactory(ProductFactory)
    s3_key = factory.LazyAttribute(lambda o: f"models/{o.product.slug}.glb")
    s3_bucket = "test-ar-bucket"
    original_filename = factory.LazyAttribute(lambda o: f"{o.product.slug}.glb")
    file_size = factory.Faker("random_int", min=100000, max=50000000)  # 0.1MB to 50MB
    content_type = "model/gltf-binary"
    uploaded_by = factory.SubFactory(UserFactory)


class CartFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Cart

    user = factory.SubFactory(UserFactory)


class CartItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CartItem

    cart = factory.SubFactory(CartFactory)
    product = factory.SubFactory(ProductFactory)
    quantity = factory.Faker("random_int", min=1, max=5)


class OrderFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Order

    buyer = factory.SubFactory(UserFactory)
    status = "payment_confirmed"
    payment_status = "paid"
    subtotal = factory.LazyFunction(lambda: Decimal(f"{random.randint(50, 500)}.00"))
    shipping_cost = Decimal("0.00")
    tax_amount = Decimal("0.00")
    discount_amount = Decimal("0.00")
    total_amount = factory.LazyAttribute(lambda o: o.subtotal + o.shipping_cost + o.tax_amount - o.discount_amount)
    shipping_address = factory.LazyAttribute(
        lambda o: {  # o here is the Order instance being built
            "street": fake.street_address(),
            "city": fake.city(),
            "country": fake.country(),
            "postal_code": fake.postcode(),
        }
    )


class OrderItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = OrderItem

    order = factory.SubFactory(OrderFactory)
    product = factory.SubFactory(ProductFactory)
    seller = factory.LazyAttribute(lambda o: o.product.seller)
    quantity = factory.Faker("random_int", min=1, max=3)

    @factory.lazy_attribute
    def unit_price(self):
        return self.product.price

    @factory.lazy_attribute
    def total_price(self):
        return self.unit_price * self.quantity

    product_name = factory.LazyAttribute(lambda o: o.product.name)
    product_description = factory.LazyAttribute(lambda o: o.product.description)
    product_image = ""


class PaymentTrackerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PaymentTracker

    id = factory.LazyFunction(uuid.uuid4)
    stripe_payment_intent_id = factory.Sequence(lambda n: f"pi_test_{n}")
    order = factory.SubFactory(OrderFactory)
    user = factory.SubFactory(UserFactory)
    transaction_type = "payment"
    status = "succeeded"
    amount = factory.LazyAttribute(lambda o: o.order.total_amount)
    currency = "USD"


class PaymentTransactionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PaymentTransaction

    id = factory.LazyFunction(uuid.uuid4)
    stripe_payment_intent_id = factory.Sequence(lambda n: f"pi_test_{n}")
    stripe_checkout_session_id = factory.Sequence(lambda n: f"cs_test_{n}")
    order = factory.SubFactory(OrderFactory)
    seller = factory.SubFactory(SellerFactory)
    buyer = factory.SubFactory(UserFactory)
    status = "completed"
    gross_amount = factory.LazyFunction(lambda: Decimal(f"{random.randint(50, 500)}.00"))
    platform_fee = factory.LazyAttribute(lambda o: o.gross_amount * Decimal("0.10"))
    stripe_fee = factory.LazyAttribute(lambda o: o.gross_amount * Decimal("0.029") + Decimal("0.30"))
    net_amount = factory.LazyAttribute(lambda o: o.gross_amount - o.platform_fee - o.stripe_fee)
    currency = "USD"
    item_count = 1
    item_names = "Test Product"


class PayoutFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Payout

    id = factory.LazyFunction(uuid.uuid4)
    stripe_payout_id = factory.Sequence(lambda n: f"po_test_{n}")
    seller = factory.SubFactory(SellerFactory)
    status = "paid"
    amount_cents = factory.LazyAttribute(lambda o: int(o.amount_decimal * 100))
    amount_decimal = factory.LazyFunction(lambda: Decimal(f"{random.randint(100, 1000)}.00"))
    currency = "USD"
    payout_type = "standard"


class PayoutItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PayoutItem

    id = factory.LazyFunction(uuid.uuid4)
    payout = factory.SubFactory(PayoutFactory)
    payment_transfer = factory.SubFactory(PaymentTransactionFactory)
    transfer_amount = factory.LazyAttribute(lambda o: o.payment_transfer.net_amount)
    transfer_currency = "USD"
    transfer_date = factory.LazyFunction(uuid.uuid4)  # Placeholder or timezone.now via LazyFunction if imported


class ExchangeRateFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ExchangeRate

    base_currency = "USD"
    target_currency = factory.Iterator(["EUR", "GBP", "CAD"])
    rate = factory.LazyFunction(lambda: Decimal(f"{random.uniform(0.5, 1.5):.4f}"))
    source = "test_factory"
