from rest_framework import serializers

from .models import AlertDigest, EmailDelivery, UserNewsDelivery
from news.serializers import StorySerializer


class AlertDigestSerializer(serializers.ModelSerializer):
    stories = StorySerializer(many=True, read_only=True)

    class Meta:
        model = AlertDigest
        fields = (
            "id",
            "digest_type",
            "subject",
            "body_text",
            "body_html",
            "scheduled_for",
            "sent_at",
            "stories",
            "created_at",
        )


class EmailDeliverySerializer(serializers.ModelSerializer):
    digest = AlertDigestSerializer(read_only=True)

    class Meta:
        model = EmailDelivery
        fields = ("id", "status", "subject", "provider_message_id", "sent_at", "error_message", "digest")


class UserNewsDeliverySerializer(serializers.ModelSerializer):
    story = StorySerializer(read_only=True)

    class Meta:
        model = UserNewsDelivery
        fields = ("id", "scope", "first_sent_at", "last_sent_at", "story")
