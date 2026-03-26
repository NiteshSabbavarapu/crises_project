from django.conf import settings
from django.db import models

from locations.models import Area, City, Country, State


class UserLocationPreference(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="location_preferences"
    )
    country = models.ForeignKey(Country, on_delete=models.SET_NULL, null=True, blank=True)
    state = models.ForeignKey(State, on_delete=models.SET_NULL, null=True, blank=True)
    city = models.ForeignKey(City, on_delete=models.SET_NULL, null=True, blank=True)
    area = models.ForeignKey(Area, on_delete=models.SET_NULL, null=True, blank=True)
    pincode = models.CharField(max_length=12, blank=True)
    lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_primary = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_primary", "-updated_at"]

    def __str__(self):
        return f"{self.user.email or self.user.username} @ {self.city or self.pincode}"


class UserAlertPreference(models.Model):
    class Frequency(models.TextChoices):
        EVERY_30_MIN = "30min", "Every 30 Minutes"
        HOURLY = "hourly", "Hourly"
        CRITICAL_ONLY = "critical_only", "Critical Only"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="alert_preference"
    )
    frequency = models.CharField(
        max_length=20, choices=Frequency.choices, default=Frequency.CRITICAL_ONLY
    )
    categories = models.JSONField(default=list, blank=True)
    email_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email or self.user.username} - {self.frequency}"


class UserActionProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="action_profile"
    )
    household_size = models.PositiveIntegerField(default=1)
    has_vehicle = models.BooleanField(default=False)
    medical_needs = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Action profile for {self.user.email or self.user.username}"
