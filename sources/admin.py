from django.contrib import admin

from .models import Source


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "credibility_tier", "coverage_scope", "is_official", "is_active")
    list_filter = ("kind", "credibility_tier", "coverage_scope", "is_official", "is_active")
    search_fields = ("name", "base_url", "feed_url")
