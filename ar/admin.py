from django.contrib import admin

from .models import ProductARModel


@admin.register(ProductARModel)
class ProductARModelAdmin(admin.ModelAdmin):
    list_display = ("product", "original_filename", "file_size", "uploaded_by", "uploaded_at")
    search_fields = ("product__name", "original_filename", "product__slug")
    raw_id_fields = ("product", "uploaded_by")
