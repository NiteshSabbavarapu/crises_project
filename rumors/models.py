from django.conf import settings
from django.db import models

from locations.models import Area, City
from news.models import RawIngestItem, Story


class RumorClaim(models.Model):
    """User-submitted claim that should be checked against verified crisis intelligence."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"

    submitter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rumor_claims",
    )
    text = models.TextField(help_text="Original rumor text, WhatsApp message, or claim submitted by the user.")
    city = models.ForeignKey(City, on_delete=models.SET_NULL, null=True, blank=True, help_text="City inferred or chosen for this rumor.")
    area = models.ForeignKey(Area, on_delete=models.SET_NULL, null=True, blank=True, help_text="Area inferred or chosen for this rumor.")
    pincode = models.CharField(max_length=12, blank=True, help_text="Optional pincode for location matching.")
    extracted_entities = models.JSONField(default=list, blank=True, help_text="Parsed entities or keywords used during verification.")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Rumor Claim"
        verbose_name_plural = "Rumor Claims"

    def __str__(self):
        return f"Claim #{self.pk or 'new'} - {self.status}"


class RumorVerdict(models.Model):
    """Verification outcome for a rumor claim."""

    class Verdict(models.TextChoices):
        VERIFIED = "verified", "Verified"
        UNCONFIRMED = "unconfirmed", "Unconfirmed"
        FALSE_DEBUNKED = "false_debunked", "False - Debunked"

    claim = models.OneToOneField(RumorClaim, on_delete=models.CASCADE, related_name="verdict")
    verdict = models.CharField(max_length=20, choices=Verdict.choices, help_text="Final classification returned to the user.")
    confidence = models.PositiveSmallIntegerField(default=0, help_text="System confidence from 0 to 100.")
    explanation = models.TextField(help_text="Human-readable explanation for the verdict.")
    official_link = models.URLField(blank=True, help_text="Most relevant official clarification or confirmation link.")
    verified_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-verified_at"]
        verbose_name = "Rumor Verdict"
        verbose_name_plural = "Rumor Verdicts"

    def __str__(self):
        return f"Verdict for claim #{self.claim_id}: {self.verdict}"


class RumorEvidence(models.Model):
    """Evidence item that supports a rumor verdict."""

    verdict = models.ForeignKey(RumorVerdict, on_delete=models.CASCADE, related_name="evidence")
    story = models.ForeignKey(Story, on_delete=models.SET_NULL, null=True, blank=True, help_text="Linked normalized story, if available.")
    raw_item = models.ForeignKey(RawIngestItem, on_delete=models.SET_NULL, null=True, blank=True, help_text="Linked raw source item, if available.")
    url = models.URLField(blank=True, help_text="Direct evidence URL shown to the user.")
    source_name = models.CharField(max_length=120, blank=True, help_text="Display name of the supporting source.")
    note = models.CharField(max_length=255, blank=True, help_text="Short note describing why this evidence matters.")

    class Meta:
        verbose_name = "Rumor Evidence"
        verbose_name_plural = "Rumor Evidence"

    def __str__(self):
        return self.source_name or self.url or f"Evidence #{self.pk}"
