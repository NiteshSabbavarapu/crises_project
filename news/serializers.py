from rest_framework import serializers

from .models import Story, StoryLocation, StorySourceEvidence, StoryTag


class StorySourceEvidenceSerializer(serializers.ModelSerializer):
    source_name = serializers.CharField(source="raw_item.source.name", read_only=True)
    url = serializers.URLField(source="raw_item.url", read_only=True)
    headline = serializers.CharField(source="raw_item.headline", read_only=True)

    class Meta:
        model = StorySourceEvidence
        fields = ("id", "source_name", "url", "headline", "is_primary", "note")


class StoryLocationSerializer(serializers.ModelSerializer):
    country_name = serializers.CharField(source="country.name", read_only=True)
    state_name = serializers.CharField(source="state.name", read_only=True)
    city_name = serializers.CharField(source="city.name", read_only=True)
    area_name = serializers.CharField(source="area.name", read_only=True)

    class Meta:
        model = StoryLocation
        fields = (
            "country_name",
            "state_name",
            "city_name",
            "area_name",
            "pincode",
            "relevance_score",
        )


class StoryTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoryTag
        fields = ("name",)


class StorySerializer(serializers.ModelSerializer):
    evidence = StorySourceEvidenceSerializer(many=True, read_only=True)
    locations = StoryLocationSerializer(many=True, read_only=True)
    tags = StoryTagSerializer(many=True, read_only=True)

    class Meta:
        model = Story
        fields = (
            "id",
            "headline",
            "summary",
            "impact_summary",
            "action_summary",
            "category",
            "severity",
            "status",
            "priority_score",
            "confidence_score",
            "official_resource_url",
            "source_count",
            "published_at",
            "detected_at",
            "evidence",
            "locations",
            "tags",
        )
