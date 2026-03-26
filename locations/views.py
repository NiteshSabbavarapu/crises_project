from rest_framework import generics, permissions

from .models import Area, City
from .serializers import AreaSerializer, CitySerializer


class CityListView(generics.ListAPIView):
    serializer_class = CitySerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        queryset = City.objects.filter(is_active=True).select_related("state__country")
        state = self.request.query_params.get("state")
        country = self.request.query_params.get("country")
        if state:
            queryset = queryset.filter(state_id=state)
        if country:
            queryset = queryset.filter(state__country_id=country)
        return queryset


class AreaListView(generics.ListAPIView):
    serializer_class = AreaSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        queryset = Area.objects.filter(is_active=True).select_related("city")
        city = self.request.query_params.get("city")
        if city:
            queryset = queryset.filter(city_id=city)
        return queryset
