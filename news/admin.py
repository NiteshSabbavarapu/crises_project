from django.contrib import admin

from .models import RawIngestItem, Story, StoryLocation, StorySourceEvidence, StoryTag


class StorySourceEvidenceInline(admin.TabularInline):
    model = StorySourceEvidence
    extra = 0


class StoryLocationInline(admin.TabularInline):
    model = StoryLocation
    extra = 0


class StoryTagInline(admin.TabularInline):
    model = StoryTag
    extra = 0


@admin.register(RawIngestItem)
class RawIngestItemAdmin(admin.ModelAdmin):
    list_display = ("headline", "source", "published_at", "fetched_at")
    list_filter = ("source",)
    search_fields = ("headline", "url", "normalized_key")


@admin.register(Story)
class StoryAdmin(admin.ModelAdmin):
    list_display = ("headline", "category", "severity", "status", "priority_score", "source_count")
    list_filter = ("category", "severity", "status")
    search_fields = ("headline", "summary", "normalized_key")
    inlines = [StorySourceEvidenceInline, StoryLocationInline, StoryTagInline]
