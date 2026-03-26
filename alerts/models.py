from django.conf import settings
from django.db import models

from news.models import Story


class AlertDecision(models.Model):
    class Mode(models.TextChoices):
        IMMEDIATE = "immediate", "Immediate"
        DIGEST = "digest", "Digest"
        DASHBOARD_ONLY = "dashboard_only", "Dashboard Only"
        SKIPPED = "skipped", "Skipped"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="alert_decisions"
    )
    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name="alert_decisions")
    mode = models.CharField(max_length=20, choices=Mode.choices)
    should_send = models.BooleanField(default=False)
    score_snapshot = models.PositiveSmallIntegerField(default=0)
    reasons = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("user", "story", "mode")


class AlertDigest(models.Model):
    class DigestType(models.TextChoices):
        IMMEDIATE = "immediate", "Immediate"
        SCHEDULED = "scheduled", "Scheduled"
        TEST = "test", "Test"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="alert_digests"
    )
    digest_type = models.CharField(max_length=20, choices=DigestType.choices)
    subject = models.CharField(max_length=255)
    body_text = models.TextField()
    body_html = models.TextField(blank=True)
    stories = models.ManyToManyField(Story, related_name="alert_digests", blank=True)
    scheduled_for = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class EmailDelivery(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="email_deliveries"
    )
    digest = models.ForeignKey(
        AlertDigest, on_delete=models.CASCADE, related_name="deliveries", null=True, blank=True
    )
    story = models.ForeignKey(
        Story, on_delete=models.SET_NULL, related_name="email_deliveries", null=True, blank=True
    )
    provider_message_id = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    subject = models.CharField(max_length=255)
    response_body = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
