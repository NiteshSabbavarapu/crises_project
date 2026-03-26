from django.contrib import admin

from .models import UserActionProfile, UserAlertPreference, UserLocationPreference


@admin.register(UserLocationPreference)
class UserLocationPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "city", "area", "pincode", "is_primary", "updated_at")
    list_filter = ("is_primary", "city")
    search_fields = ("user__username", "user__email", "pincode")


@admin.register(UserAlertPreference)
class UserAlertPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "frequency", "email_enabled", "updated_at")
    list_filter = ("frequency", "email_enabled")
    search_fields = ("user__username", "user__email")


@admin.register(UserActionProfile)
class UserActionProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "household_size", "has_vehicle", "medical_needs", "updated_at")
    search_fields = ("user__username", "user__email", "medical_needs")
