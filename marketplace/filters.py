import django_filters
from django.db.models import F, Q

from .models import Category, Product


class ProductFilter(django_filters.FilterSet):
    """
    Filter for products with various filtering options
    """

    # Price range filters
    min_price = django_filters.NumberFilter(field_name="price", lookup_expr="gte")
    max_price = django_filters.NumberFilter(field_name="price", lookup_expr="lte")

    # Category filters
    category = django_filters.ModelChoiceFilter(queryset=Category.objects.filter(is_active=True))
    category_slug = django_filters.CharFilter(field_name="category__slug", lookup_expr="exact")

    # Condition filter
    condition = django_filters.MultipleChoiceFilter(choices=Product.CONDITION_CHOICES, method="filter_condition")

    # Brand filter
    brand = django_filters.CharFilter(lookup_expr="icontains")
    brands = django_filters.CharFilter(method="filter_brands")

    # Boolean filters
    is_featured = django_filters.BooleanFilter()
    is_digital = django_filters.BooleanFilter()
    is_on_sale = django_filters.BooleanFilter(method="filter_on_sale")
    in_stock = django_filters.BooleanFilter(method="filter_in_stock")

    # Seller filter
    seller = django_filters.CharFilter(field_name="seller__username", lookup_expr="icontains")
    seller_id = django_filters.NumberFilter(field_name="seller__id")

    # Rating filter
    min_rating = django_filters.NumberFilter(method="filter_min_rating")

    # Search in multiple fields
    search = django_filters.CharFilter(method="filter_search")

    # Tags filter
    tags = django_filters.CharFilter(method="filter_tags")

    # Colors filter
    colors = django_filters.CharFilter(method="filter_colors")

    # Sorting options
    ordering = django_filters.OrderingFilter(
        fields=(
            ("created_at", "created_at"),
            ("price", "price"),
            ("view_count", "popularity"),
            ("favorite_count", "favorites"),
            ("name", "name"),
        ),
        field_labels={
            "created_at": "Date Created",
            "price": "Price",
            "popularity": "Popularity",
            "favorites": "Favorites",
            "name": "Name",
        },
    )

    class Meta:
        model = Product
        fields = {
            "name": ["icontains"],
            "description": ["icontains"],
            "brand": ["icontains"],
            "model": ["icontains"],
            "condition": ["exact"],
            "is_featured": ["exact"],
            "is_digital": ["exact"],
            "category": ["exact"],
        }

    def filter_condition(self, queryset, name, value):
        if value:
            return queryset.filter(condition__in=value)
        return queryset

    def filter_brands(self, queryset, name, value):
        """Filter by multiple brands separated by comma"""
        if value:
            brand_list = [brand.strip() for brand in value.split(",")]
            return queryset.filter(brand__in=brand_list)
        return queryset

    def filter_on_sale(self, queryset, name, value):
        if value:
            return queryset.filter(original_price__isnull=False, original_price__gt=F("price"))
        elif value is False:
            return queryset.filter(Q(original_price__isnull=True) | Q(original_price__lte=F("price")))
        return queryset

    def filter_in_stock(self, queryset, name, value):
        if value:
            return queryset.filter(stock_quantity__gt=0)
        elif value is False:
            return queryset.filter(stock_quantity=0)
        return queryset

    def filter_min_rating(self, queryset, name, value):
        """Filter products with minimum average rating"""
        if value:
            # This would require a more complex annotation in the view
            # For now, we'll use a simple approach
            product_ids = []
            for product in queryset:
                if product.average_rating >= value:
                    product_ids.append(product.id)
            return queryset.filter(id__in=product_ids)
        return queryset

    def filter_search(self, queryset, name, value):
        """Search across multiple fields"""
        if value:
            return queryset.filter(
                Q(name__icontains=value)
                | Q(description__icontains=value)
                | Q(brand__icontains=value)
                | Q(model__icontains=value)
                | Q(tags__icontains=value)
            )
        return queryset

    def filter_tags(self, queryset, name, value):
        """Filter by tags (comma-separated)"""
        if value:
            tag_list = [tag.strip() for tag in value.split(",")]
            query = Q()
            for tag in tag_list:
                query |= Q(tags__icontains=tag)
            return queryset.filter(query)
        return queryset

    def filter_colors(self, queryset, name, value):
        """Filter by colors (comma-separated)"""
        if value:
            color_list = [color.strip() for color in value.split(",")]
            query = Q()
            for color in color_list:
                query |= Q(colors__icontains=color)
            return queryset.filter(query)
        return queryset
