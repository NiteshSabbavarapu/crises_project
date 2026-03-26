from django.urls import path

from .views import AlertDetailView, AlertListView, AlertTestSendView, UserNewsDeliveryListView

urlpatterns = [
    path("", AlertListView.as_view(), name="alert-list"),
    path("news", UserNewsDeliveryListView.as_view(), name="alert-news-list"),
    path("test-send", AlertTestSendView.as_view(), name="alert-test-send"),
    path("<int:pk>", AlertDetailView.as_view(), name="alert-detail"),
]
