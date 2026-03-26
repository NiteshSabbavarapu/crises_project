from django.urls import include, path
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthcheckView(APIView):
    permission_classes = []

    def get(self, request):
        return Response({"status": "ok", "service": "crisissync"})


urlpatterns = [
    path("health/", HealthcheckView.as_view(), name="healthcheck"),
    path("auth/", include("accounts.urls")),
    path("locations/", include("locations.urls")),
    path("profile/", include("accounts.profile_urls")),
    path("stories/", include("news.urls")),
    path("alerts/", include("alerts.urls")),
    path("rumors/", include("rumors.urls")),
]
