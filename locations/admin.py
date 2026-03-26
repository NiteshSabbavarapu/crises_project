from django.contrib import admin

from .models import Area, City, Country, State


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name", "code")


@admin.register(State)
class StateAdmin(admin.ModelAdmin):
    list_display = ("name", "country", "code")
    list_filter = ("country",)
    search_fields = ("name", "code")


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ("name", "state", "is_active")
    list_filter = ("state", "is_active")
    search_fields = ("name", "slug")


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "pincode", "is_active")
    list_filter = ("city", "is_active")
    search_fields = ("name", "pincode")
