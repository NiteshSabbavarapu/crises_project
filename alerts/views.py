from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from news.models import Story

from .models import AlertDigest, UserNewsDelivery
from .serializers import AlertDigestSerializer, UserNewsDeliverySerializer
from .services import build_digest_body, build_digest_html, build_digest_subject, send_digest


class AlertListView(generics.ListAPIView):
    serializer_class = AlertDigestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return AlertDigest.objects.filter(user=self.request.user).prefetch_related("stories")


class AlertDetailView(generics.RetrieveAPIView):
    serializer_class = AlertDigestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return AlertDigest.objects.filter(user=self.request.user).prefetch_related("stories")


class UserNewsDeliveryListView(generics.ListAPIView):
    serializer_class = UserNewsDeliverySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = UserNewsDelivery.objects.filter(user=self.request.user).select_related("story")
        scope = self.request.query_params.get("scope")
        if scope:
            queryset = queryset.filter(scope=scope)
        return queryset.prefetch_related(
            "story__evidence__raw_item__source", "story__locations__city", "story__locations__area", "story__tags"
        )


class AlertTestSendView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not request.user.is_staff and not request.user.is_superuser:
            return Response({"detail": "Test send is admin-only."}, status=status.HTTP_403_FORBIDDEN)
        story = Story.objects.order_by("-priority_score").first()
        if not story:
            return Response({"detail": "No stories available."}, status=status.HTTP_400_BAD_REQUEST)
        digest = AlertDigest.objects.create(
            user=request.user,
            digest_type=AlertDigest.DigestType.TEST,
            subject=build_digest_subject(story, AlertDigest.DigestType.TEST),
            body_text=build_digest_body(request.user, [story]),
            body_html=build_digest_html(request.user, [story]),
        )
        digest.stories.add(story)
        delivery = send_digest(digest)
        return Response(
            {
                "digest": AlertDigestSerializer(digest).data,
                "delivery_status": delivery.status,
            }
        )
