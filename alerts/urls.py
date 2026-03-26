from django.urls import path

from .views import AlertDetailView, AlertListView, AlertTestSendView

urlpatterns = [
    path("", AlertListView.as_view(), name="alert-list"),
    path("test-send", AlertTestSendView.as_view(), name="alert-test-send"),
    path("<int:pk>", AlertDetailView.as_view(), name="alert-detail"),
]
