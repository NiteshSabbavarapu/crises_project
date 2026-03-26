from django.db import models


class Source(models.Model):
    """Trusted source registry used by the ingestion pipeline."""

    class Kind(models.TextChoices):
        RSS = "rss", "RSS"
        API = "api", "API"
        HTML = "html", "HTML"

    class CredibilityTier(models.TextChoices):
        OFFICIAL = "official", "Official"
        TIER_1 = "tier_1", "Tier 1"
        TIER_2 = "tier_2", "Tier 2"

    class CoverageScope(models.TextChoices):
        LOCAL = "local", "Local"
        STATE = "state", "State"
        NATIONAL = "national", "National"
        GLOBAL = "global", "Global"

    name = models.CharField(max_length=120, unique=True, help_text="Display name for the publication or authority.")
    kind = models.CharField(max_length=20, choices=Kind.choices, help_text="How CrisisSync fetches content from this source.")
    base_url = models.URLField(help_text="Canonical home page for the source.")
    feed_url = models.URLField(blank=True, help_text="Feed or API endpoint used during ingestion.")
    credibility_tier = models.CharField(
        max_length=20,
        choices=CredibilityTier.choices,
        default=CredibilityTier.TIER_1,
        help_text="Trust tier used when verifying stories.",
    )
    is_official = models.BooleanField(default=False, help_text="True for government or other official authorities.")
    is_active = models.BooleanField(default=True, help_text="Inactive sources are skipped by ingestion jobs.")
    coverage_scope = models.CharField(
        max_length=20,
        choices=CoverageScope.choices,
        default=CoverageScope.NATIONAL,
        help_text="Primary geography covered by this source.",
    )
    metadata = models.JSONField(default=dict, blank=True, help_text="Connector-specific settings or diagnostics.")
    last_fetched_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Trusted Source"
        verbose_name_plural = "Trusted Sources"

    def __str__(self):
        return f"{self.name} [{self.kind}]"
