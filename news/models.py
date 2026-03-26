from django.db import models

from locations.models import Area, City, Country, State
from sources.models import Source


class RawIngestItem(models.Model):
    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name="raw_items")
    external_id = models.CharField(max_length=255, blank=True)
    url = models.URLField()
    headline = models.CharField(max_length=500)
    raw_body = models.TextField(blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    fetched_at = models.DateTimeField(auto_now_add=True)
    checksum = models.CharField(max_length=64)
    normalized_key = models.CharField(max_length=255, blank=True, db_index=True)

    class Meta:
        ordering = ["-published_at", "-fetched_at"]
        unique_together = ("source", "url", "checksum")

    def __str__(self):
        return self.headline


class Story(models.Model):
    class Category(models.TextChoices):
        SUPPLY_CRISIS = "supply_crisis", "Supply Crisis"
        WEATHER = "weather", "Weather"
        CIVIL_UNREST = "civil_unrest", "Civil Unrest"
        PRICE_SURGE = "price_surge", "Price Surge"
        HEALTH = "health", "Health"
        GENERAL = "general", "General"

    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    class Status(models.TextChoices):
        VERIFIED = "verified", "Verified"
        UNCONFIRMED = "unconfirmed", "Unconfirmed"
        DEBUNKED = "debunked", "Debunked"

    headline = models.CharField(max_length=500)
    summary = models.TextField(blank=True)
    impact_summary = models.TextField(blank=True)
    action_summary = models.TextField(blank=True)
    category = models.CharField(max_length=32, choices=Category.choices, default=Category.GENERAL)
    severity = models.CharField(max_length=16, choices=Severity.choices, default=Severity.MEDIUM)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.UNCONFIRMED)
    priority_score = models.PositiveSmallIntegerField(default=0)
    confidence_score = models.PositiveSmallIntegerField(default=0)
    official_resource_url = models.URLField(blank=True)
    source_count = models.PositiveSmallIntegerField(default=0)
    normalized_key = models.CharField(max_length=255, unique=True)
    metadata = models.JSONField(default=dict, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    detected_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-priority_score", "-published_at", "-detected_at"]

    def __str__(self):
        return self.headline


class StorySourceEvidence(models.Model):
    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name="evidence")
    raw_item = models.ForeignKey(RawIngestItem, on_delete=models.CASCADE, related_name="story_links")
    is_primary = models.BooleanField(default=False)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = ("story", "raw_item")


class StoryLocation(models.Model):
    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name="locations")
    country = models.ForeignKey(Country, on_delete=models.SET_NULL, null=True, blank=True)
    state = models.ForeignKey(State, on_delete=models.SET_NULL, null=True, blank=True)
    city = models.ForeignKey(City, on_delete=models.SET_NULL, null=True, blank=True)
    area = models.ForeignKey(Area, on_delete=models.SET_NULL, null=True, blank=True)
    pincode = models.CharField(max_length=12, blank=True)
    relevance_score = models.PositiveSmallIntegerField(default=50)

    class Meta:
        unique_together = ("story", "country", "state", "city", "area", "pincode")


class StoryTag(models.Model):
    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name="tags")
    name = models.CharField(max_length=64)

    class Meta:
        unique_together = ("story", "name")

    def __str__(self):
        return self.name
