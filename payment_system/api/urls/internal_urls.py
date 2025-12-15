from django.urls import path

from payment_system.api.views import internal_views as views


app_name = "payment_system_internal"

urlpatterns = [
    path("payments/<uuid:order_id>/status/", views.get_payment_status_internal, name="get_payment_status_internal"),
    path(
        "payouts/seller/<uuid:seller_id>/balance/",
        views.get_seller_balance_internal,
        name="get_seller_balance_internal",
    ),
]
