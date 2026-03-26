from django.urls import path

from .views import RumorClaimDetailView, RumorClaimListCreateView

urlpatterns = [
    path("", RumorClaimListCreateView.as_view(), name="rumor-list-create"),
    path("<int:pk>", RumorClaimDetailView.as_view(), name="rumor-detail"),
]
