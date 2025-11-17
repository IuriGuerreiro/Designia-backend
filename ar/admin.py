from django.contrib import admin

from .models import ProductARModel, ProductARModelDownload


@admin.register(ProductARModel)
class ProductARModelAdmin(admin.ModelAdmin):
    list_display = ("product", "original_filename", "file_size", "uploaded_by", "uploaded_at")
    search_fields = ("product__name", "original_filename", "product__slug")
    raw_id_fields = ("product", "uploaded_by")


@admin.register(ProductARModelDownload)
class ProductARModelDownloadAdmin(admin.ModelAdmin):
    list_display = (
        "file_name",
        "user",
        "product_display",
        "platform",
        "local_path",
        "created_at",
    )
    list_filter = ("platform", "created_at")
    search_fields = ("file_name", "local_path", "user__username", "product_model__product__name")
    raw_id_fields = ("user", "product_model")

    @staticmethod
    def product_display(obj):
        return obj.product_model.product.name

    product_display.short_description = "Product"
