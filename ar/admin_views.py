from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView, View

from utils.s3_storage import S3StorageError, get_s3_storage

from .models import ProductARModel


@method_decorator(staff_member_required, name="dispatch")
class ProductARModelAdminListView(TemplateView):
    """Staff-only view that lists all ProductARModel entries with quick download controls."""

    template_name = "admin/ar_model_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(admin.site.each_context(self.request))

        context["ar_models"] = ProductARModel.objects.select_related("product", "uploaded_by").order_by("-uploaded_at")
        context["page_title"] = "Product 3D Models"
        return context


@method_decorator(staff_member_required, name="dispatch")
class ProductARModelAdminDownloadView(View):
    """Generates a presigned download URL for an AR model and redirects the admin to it."""

    def get(self, request, pk: int):
        ar_model = get_object_or_404(ProductARModel, pk=pk)

        try:
            storage = get_s3_storage()
            download_url = storage.download_product_3d_model(ar_model.s3_key, as_url=True, expires_in=300)
            return redirect(download_url)
        except S3StorageError as exc:
            messages.error(request, f"Unable to generate download link: {exc}")
            return redirect(reverse("admin-ar-models"))
