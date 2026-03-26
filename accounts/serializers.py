from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from accounts.models import UserActionProfile, UserAlertPreference, UserLocationPreference
from locations.models import Area, City, Country, State

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ("id", "username", "email", "password", "password_confirm", "first_name", "last_name")

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        validate_password(attrs["password"])
        return attrs

    def create(self, validated_data):
        validated_data.pop("password_confirm")
        password = validated_data.pop("password")
        if not validated_data.get("username"):
            validated_data["username"] = validated_data["email"]
        user = User.objects.create_user(password=password, **validated_data)
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
