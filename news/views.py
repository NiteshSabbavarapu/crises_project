from django.utils.dateparse import parse_datetime
from rest_framework import generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from .models import Story
from .serializers import StorySerializer


def _get_required_user_primary_location(user):
    if not user.is_authenticated:
        raise NotFound(detail="User location not found.")
    location = user.location_preferences.filter(is_primary=True).first()
    if not location:
        raise NotFound(detail="User location not found.")
    return location


def _filter_queryset_for_user_primary_location(queryset, user):
    location = _get_required_user_primary_location(user)
    if location.state_id:
        return queryset.filter(locations__state_id=location.state_id)
    if location.area_id:
        return queryset.filter(locations__area_id=location.area_id)
    if location.pincode:
        return queryset.filter(locations__pincode=location.pincode)
    if location.city_id:
        return queryset.filter(locations__city_id=location.city_id)
    raise NotFound(detail="User location not found.")


class StoryListView(generics.ListAPIView):
    serializer_class = StorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = Story.objects.prefetch_related(
            "evidence__raw_item__source", "locations__city", "locations__area", "tags"
        )
        queryset = _filter_queryset_for_user_primary_location(queryset, self.request.user)
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


class CompleteNewsListView(generics.ListAPIView):
    serializer_class = StorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = Story.objects.prefetch_related(
            "evidence__raw_item__source", "locations__city", "locations__area", "tags"
        ).order_by("-published_at", "-detected_at", "-priority_score")
        params = self.request.query_params
        if params.get("category"):
            queryset = queryset.filter(category=params["category"])
        if params.get("status"):
            queryset = queryset.filter(status=params["status"])
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
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        return _filter_queryset_for_user_primary_location(queryset, self.request.user).distinct()


class FakeNewsListView(generics.ListAPIView):
    serializer_class = StorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = Story.objects.filter(status=Story.Status.DEBUNKED).prefetch_related(
            "evidence__raw_item__source", "locations__city", "locations__area", "tags"
        )
        return _filter_queryset_for_user_primary_location(queryset, self.request.user).distinct()


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def critical_stories(request):
    stories = Story.objects.filter(priority_score__gte=80).prefetch_related(
        "evidence__raw_item__source", "locations__city", "locations__area", "tags"
    )
    stories = _filter_queryset_for_user_primary_location(stories, request.user).distinct()
    return Response(StorySerializer(stories, many=True).data)
