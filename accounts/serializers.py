from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework.exceptions import NotFound

from accounts.models import UserActionProfile, UserAlertPreference, UserLocationPreference
from locations.models import Area, City, Country, State

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True, min_length=8)
    country = serializers.IntegerField(write_only=True, required=False)
    state = serializers.IntegerField(write_only=True, required=False)
    city = serializers.IntegerField(write_only=True, required=False)
    area = serializers.IntegerField(write_only=True, required=False)
    pincode = serializers.CharField(write_only=True, required=False, allow_blank=True)
    lat = serializers.DecimalField(write_only=True, required=False, allow_null=True, max_digits=9, decimal_places=6)
    lng = serializers.DecimalField(write_only=True, required=False, allow_null=True, max_digits=9, decimal_places=6)

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "password",
            "password_confirm",
            "first_name",
            "last_name",
            "country",
            "state",
            "city",
            "area",
            "pincode",
            "lat",
            "lng",
        )

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        validate_password(attrs["password"])
        required_location_fields = ("country", "state", "city", "area")
        missing = [field for field in required_location_fields if not attrs.get(field)]
        if missing:
            raise NotFound(detail=f"Location is required. Missing fields: {', '.join(missing)}.")
        country = Country.objects.filter(id=attrs["country"]).first()
        if not country:
            raise NotFound(detail="Country not found.")
        state = State.objects.filter(id=attrs["state"]).select_related("country").first()
        if not state:
            raise NotFound(detail="State not found.")
        city = City.objects.filter(id=attrs["city"]).select_related("state__country").first()
        if not city:
            raise NotFound(detail="City not found.")
        area = Area.objects.filter(id=attrs["area"]).select_related("city__state__country").first()
        if not area:
            raise NotFound(detail="Area not found.")
        if state.country_id != country.id:
            raise serializers.ValidationError({"state": "State does not belong to country."})
        if city.state_id != state.id:
            raise serializers.ValidationError({"city": "City does not belong to state."})
        if area.city_id != city.id:
            raise serializers.ValidationError({"area": "Area does not belong to city."})
        attrs["country"] = country
        attrs["state"] = state
        attrs["city"] = city
        attrs["area"] = area
        attrs["pincode"] = attrs.get("pincode") or area.pincode
        return attrs

    def create(self, validated_data):
        validated_data.pop("password_confirm")
        password = validated_data.pop("password")
        country = validated_data.pop("country")
        state = validated_data.pop("state")
        city = validated_data.pop("city")
        area = validated_data.pop("area")
        pincode = validated_data.pop("pincode", "")
        lat = validated_data.pop("lat", None)
        lng = validated_data.pop("lng", None)
        if not validated_data.get("username"):
            validated_data["username"] = validated_data["email"]
        user = User.objects.create_user(password=password, **validated_data)
        UserLocationPreference.objects.create(
            user=user,
            country=country,
            state=state,
            city=city,
            area=area,
            pincode=pincode,
            lat=lat,
            lng=lng,
            is_primary=True,
        )
        UserAlertPreference.objects.get_or_create(user=user)
        UserActionProfile.objects.get_or_create(user=user)
        return user


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "email", "first_name", "last_name")


class UserLocationPreferenceSerializer(serializers.ModelSerializer):
    country_name = serializers.CharField(source="country.name", read_only=True)
    state_name = serializers.CharField(source="state.name", read_only=True)
    city_name = serializers.CharField(source="city.name", read_only=True)
    area_name = serializers.CharField(source="area.name", read_only=True)

    class Meta:
        model = UserLocationPreference
        fields = (
            "id",
            "country",
            "country_name",
            "state",
            "state_name",
            "city",
            "city_name",
            "area",
            "area_name",
            "pincode",
            "lat",
            "lng",
            "is_primary",
        )

    def validate(self, attrs):
        country = attrs.get("country")
        state = attrs.get("state")
        city = attrs.get("city")
        area = attrs.get("area")
        if state and country and state.country_id != country.id:
            raise serializers.ValidationError("State does not belong to country.")
        if city and state and city.state_id != state.id:
            raise serializers.ValidationError("City does not belong to state.")
        if area and city and area.city_id != city.id:
            raise serializers.ValidationError("Area does not belong to city.")
        return attrs


class UserAlertPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserAlertPreference
        fields = ("frequency", "categories", "email_enabled")


class UserActionProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserActionProfile
        fields = ("household_size", "has_vehicle", "medical_needs", "notes")


class UserProfileBundleSerializer(serializers.Serializer):
    user = UserSerializer(read_only=True)
    locations = UserLocationPreferenceSerializer(many=True, read_only=True)
    alert_preference = UserAlertPreferenceSerializer(read_only=True)
    action_profile = UserActionProfileSerializer(read_only=True)
