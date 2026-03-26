from rest_framework import serializers

from .models import Area, City


class CitySerializer(serializers.ModelSerializer):
    state_name = serializers.CharField(source="state.name", read_only=True)
    country_name = serializers.CharField(source="state.country.name", read_only=True)

    class Meta:
        model = City
        fields = ("id", "name", "slug", "state_name", "country_name")


class AreaSerializer(serializers.ModelSerializer):
    city_name = serializers.CharField(source="city.name", read_only=True)

    class Meta:
        model = Area
        fields = ("id", "name", "city", "city_name", "pincode", "latitude", "longitude")
