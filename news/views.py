from django.utils.dateparse import parse_datetime
from rest_framework import generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import Story
from .serializers import StorySerializer


class StoryListView(generics.ListAPIView):
    serializer_class = StorySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        queryset = Story.objects.prefetch_related(
            "evidence__raw_item__source", "locations__city", "locations__area", "tags"
        )
        params = self.request.query_params
        if params.get("city"):
            queryset = queryset.filter(locations__city_id=params["city"])
        if params.get("area"):
            queryset = queryset.filter(locations__area_id=params["area"])
        if params.get("pincode"):
            queryset = queryset.filter(locations__pincode=params["pincode"])
        if params.get("category"):
            queryset = queryset.filter(category=params["category"])
        if params.get("status"):
            queryset = queryset.filter(status=params["status"])
        if params.get("min_priority"):
            queryset = queryset.filter(priority_score__gte=params["min_priority"])
        if params.get("since"):
            since = parse_datetime(params["since"])
            if since:
                queryset = queryset.filter(detected_at__gte=since)
        return queryset.distinct()


class StoryDetailView(generics.RetrieveAPIView):
    queryset = Story.objects.prefetch_related(
        "evidence__raw_item__source", "locations__city", "locations__area", "tags"
    )
    serializer_class = StorySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


class FakeNewsListView(generics.ListAPIView):
    serializer_class = StorySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        return Story.objects.filter(status=Story.Status.DEBUNKED).prefetch_related(
            "evidence__raw_item__source", "locations__city", "locations__area", "tags"
        )


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticatedOrReadOnly])
def critical_stories(request):
    stories = Story.objects.filter(priority_score__gte=80).prefetch_related(
        "evidence__raw_item__source", "locations__city", "locations__area", "tags"
    )
    return Response(StorySerializer(stories, many=True).data)
