from django.urls import path

from .views import ActionProfileView, AlertPreferenceView, UserLocationPreferenceView

urlpatterns = [
    path("location", UserLocationPreferenceView.as_view(), name="profile-location"),
    path("preferences", AlertPreferenceView.as_view(), name="profile-preferences"),
    path("action-profile", ActionProfileView.as_view(), name="profile-action-profile"),
]
