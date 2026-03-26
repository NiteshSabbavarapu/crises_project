from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from locations.models import Area, City, Country, State

User = get_user_model()


class AccountApiTests(APITestCase):
    def setUp(self):
        self.country = Country.objects.create(name="India", code="IN")
        self.state = State.objects.create(country=self.country, name="Telangana", code="TS")
        self.city = City.objects.create(state=self.state, name="Hyderabad")
        self.area = Area.objects.create(city=self.city, name="Banjara Hills", pincode="500034")

    def test_register_and_profile_setup(self):
        register_response = self.client.post(
            "/api/v1/auth/register",
            {
                "username": "nitesh",
                "email": "nitesh@example.com",
                "password": "VerySecurePass123",
                "password_confirm": "VerySecurePass123",
                "country": self.country.id,
                "state": self.state.id,
                "city": self.city.id,
                "area": self.area.id,
                "pincode": self.area.pincode,
            },
            format="json",
        )
        self.assertEqual(register_response.status_code, status.HTTP_201_CREATED)

        login_response = self.client.post(
            "/api/v1/auth/login",
            {"username": "nitesh", "password": "VerySecurePass123"},
            format="json",
        )
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login_response.data['access']}")

        pref_response = self.client.put(
            "/api/v1/profile/preferences",
            {"frequency": "hourly", "categories": ["supply_crisis", "weather"], "email_enabled": True},
            format="json",
        )
        self.assertEqual(pref_response.status_code, status.HTTP_200_OK)

        action_response = self.client.put(
            "/api/v1/profile/action-profile",
            {"household_size": 4, "has_vehicle": True, "medical_needs": "insulin", "notes": "elderly parents"},
            format="json",
        )
        self.assertEqual(action_response.status_code, status.HTTP_200_OK)

        me_response = self.client.get("/api/v1/auth/me")
        self.assertEqual(me_response.status_code, status.HTTP_200_OK)
        self.assertEqual(me_response.data["user"]["email"], "nitesh@example.com")
        self.assertEqual(len(me_response.data["locations"]), 1)

    def test_register_requires_location_fields(self):
        register_response = self.client.post(
            "/api/v1/auth/register",
            {
                "username": "nitesh",
                "email": "nitesh@example.com",
                "password": "VerySecurePass123",
                "password_confirm": "VerySecurePass123",
            },
            format="json",
        )

        self.assertEqual(register_response.status_code, status.HTTP_404_NOT_FOUND)
