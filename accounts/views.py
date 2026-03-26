from django.contrib.auth import get_user_model
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import UserActionProfile, UserAlertPreference, UserLocationPreference
from .serializers import (
    RegisterSerializer,
    UserActionProfileSerializer,
    UserAlertPreferenceSerializer,
    UserLocationPreferenceSerializer,
    UserSerializer,
)

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        alert_preference, _ = UserAlertPreference.objects.get_or_create(user=request.user)
        action_profile, _ = UserActionProfile.objects.get_or_create(user=request.user)
        payload = {
            "user": UserSerializer(request.user).data,
            "locations": UserLocationPreferenceSerializer(
                request.user.location_preferences.all(), many=True
            ).data,
            "alert_preference": UserAlertPreferenceSerializer(alert_preference).data,
            "action_profile": UserActionProfileSerializer(action_profile).data,
        }
        return Response(payload)


class UserLocationPreferenceView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = UserLocationPreferenceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data.get("is_primary", True):
            request.user.location_preferences.update(is_primary=False)
        location = serializer.save(user=request.user)
        return Response(UserLocationPreferenceSerializer(location).data, status=status.HTTP_201_CREATED)


class AlertPreferenceView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request):
        instance, _ = UserAlertPreference.objects.get_or_create(user=request.user)
        serializer = UserAlertPreferenceSerializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ActionProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request):
        instance, _ = UserActionProfile.objects.get_or_create(user=request.user)
        serializer = UserActionProfileSerializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
