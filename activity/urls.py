from django.urls import path

from . import views

app_name = "activity"

urlpatterns = [
    path("track/", views.track_product_activity, name="track_activity"),
    path("stats/<uuid:product_id>/", views.get_product_activity_stats, name="product_stats"),
    path("history/", views.get_user_activity_history, name="user_history"),
]
