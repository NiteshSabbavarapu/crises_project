import hashlib
import re
from collections import defaultdict

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from locations.models import Area, City
from intel.models import IntelligenceRun
from intel.services import generate_story_brief
from news.models import RawIngestItem, Story, StoryLocation, StorySourceEvidence, StoryTag


CATEGORY_KEYWORDS = {
    Story.Category.SUPPLY_CRISIS: ["shortage", "supply", "stock", "ration", "outage", "fuel"],
    Story.Category.WEATHER: ["flood", "rain", "storm", "weather", "cyclone", "heatwave"],
    Story.Category.CIVIL_UNREST: ["protest", "violence", "curfew", "riot", "unrest"],
    Story.Category.PRICE_SURGE: ["price", "inflation", "cost", "surge"],
    Story.Category.HEALTH: ["health", "hospital", "virus", "disease", "medical"],
}

SEVERITY_KEYWORDS = {
    Story.Severity.CRITICAL: ["death", "emergency", "critical", "evacuate", "urgent", "shutdown"],
    Story.Severity.HIGH: ["shortage", "flood", "protest", "disruption", "closure"],
    Story.Severity.MEDIUM: ["advisory", "warning", "delayed", "watch"],
}

ACTION_TEMPLATES = {
    Story.Category.SUPPLY_CRISIS: [
        "Buy only essentials for the next 48 hours and avoid panic purchases.",
        "Check nearby official ration or supply advisories before traveling.",
        "Keep a backup cooking or power option ready if the disruption continues.",
    ],
    Story.Category.WEATHER: [
        "Avoid low-lying roads and verify municipal traffic advisories before moving.",
        "Charge phones and keep emergency contacts accessible.",
        "Monitor official rainfall or flood-control updates for escalation.",
    ],
    Story.Category.CIVIL_UNREST: [
        "Avoid non-essential travel near affected zones until official clearance.",
        "Rely on police or district administration advisories over social forwards.",
        "Keep family members informed of a single safe meetup or communication plan.",
    ],
    Story.Category.PRICE_SURGE: [
        "Compare official rate bulletins before purchasing in bulk.",
        "Prioritize essentials and delay non-urgent discretionary purchases.",
        "Track local consumer affairs notices for stabilisation measures.",
    ],
    Story.Category.HEALTH: [
        "Follow public-health advisories and avoid crowded facilities unless necessary.",
        "Keep regular medication stocked for a few extra days.",
        "Use official helplines before visiting hospitals for non-emergencies.",
    ],
    Story.Category.GENERAL: [
        "Follow official local guidance and avoid forwarding unverified information.",
        "Check for direct operational impact in your area before acting.",
        "Keep one reliable source bookmarked for updates.",
    ],
}


def normalize_text(value):
    return re.sub(r"[^a-z0-9\s]", " ", value.lower()).strip()


def compute_checksum(*parts):
    joined = "||".join(part or "" for part in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def build_normalized_key(headline, body):
    normalized = normalize_text(f"{headline} {body}")
    tokens = [token for token in normalized.split() if len(token) > 2]
    return "-".join(tokens[:12]) or compute_checksum(headline, body)[:24]


def infer_category(text):
    normalized = normalize_text(text)
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in normalized for keyword in keywords):
            return category
    return Story.Category.GENERAL


def infer_severity(text):
    normalized = normalize_text(text)
    for severity, keywords in SEVERITY_KEYWORDS.items():
        if any(keyword in normalized for keyword in keywords):
            return severity
    return Story.Severity.LOW


def find_location_matches(text):
    normalized = normalize_text(text)
    locations = []
    for city in City.objects.filter(is_active=True):
        if city.name.lower() in normalized:
            locations.append({"city": city, "state": city.state, "country": city.state.country})
    for area in Area.objects.filter(is_active=True).select_related("city__state__country"):
        if area.name.lower() in normalized:
            locations.append(
                {
                    "area": area,
                    "city": area.city,
                    "state": area.city.state,
                    "country": area.city.state.country,
                    "pincode": area.pincode,
                }
            )
    return locations


def summarize_story(story):
    evidence = list(story.evidence.select_related("raw_item__source"))
    if not evidence:
        return "", "", ""
    fallback_actions = ACTION_TEMPLATES.get(story.category, ACTION_TEMPLATES[Story.Category.GENERAL])
    return generate_story_brief(story, fallback_actions)


def score_story(story):
    severity_weight = {
        Story.Severity.LOW: 15,
        Story.Severity.MEDIUM: 35,
        Story.Severity.HIGH: 60,
        Story.Severity.CRITICAL: 80,
    }[story.severity]
    source_bonus = min(story.source_count * 10, 20)
    official_bonus = 20 if story.evidence.filter(raw_item__source__is_official=True).exists() else 0
    recency_bonus = 0
    if story.published_at:
        age_minutes = max((timezone.now() - story.published_at).total_seconds() / 60, 0)
        if age_minutes <= settings.NEWS_FETCH_WINDOW_MINUTES:
            recency_bonus = 15
        elif age_minutes <= 120:
            recency_bonus = 8
    location_bonus = 10 if story.locations.exists() else 0
    total = min(severity_weight + source_bonus + official_bonus + recency_bonus + location_bonus, 100)
    return total


@transaction.atomic
def normalize_raw_items():
    grouped = defaultdict(list)
    for raw_item in RawIngestItem.objects.select_related("source").all():
        key = raw_item.normalized_key or build_normalized_key(raw_item.headline, raw_item.raw_body)
        if raw_item.normalized_key != key:
            raw_item.normalized_key = key
            raw_item.save(update_fields=["normalized_key"])
        grouped[key].append(raw_item)

    normalized_stories = []
    for normalized_key, items in grouped.items():
        items = sorted(items, key=lambda item: item.published_at or item.fetched_at, reverse=True)
        combined_text = " ".join([items[0].headline, items[0].raw_body])
        story, _ = Story.objects.get_or_create(
            normalized_key=normalized_key,
            defaults={
                "headline": items[0].headline,
                "category": infer_category(combined_text),
                "severity": infer_severity(combined_text),
                "published_at": items[0].published_at,
            },
        )
        story.headline = items[0].headline
        story.category = infer_category(combined_text)
        story.severity = infer_severity(combined_text)
        story.published_at = items[0].published_at
        story.save()

        StorySourceEvidence.objects.filter(story=story).exclude(raw_item__in=items).delete()
        for index, item in enumerate(items):
            StorySourceEvidence.objects.get_or_create(
                story=story, raw_item=item, defaults={"is_primary": index == 0}
            )

        locations = find_location_matches(combined_text)
        if locations:
            StoryLocation.objects.filter(story=story).delete()
            for match in locations:
                StoryLocation.objects.get_or_create(
                    story=story,
                    country=match.get("country"),
                    state=match.get("state"),
                    city=match.get("city"),
                    area=match.get("area"),
                    pincode=match.get("pincode", ""),
                    defaults={"relevance_score": 80 if match.get("area") else 60},
                )

        StoryTag.objects.get_or_create(story=story, name=story.category)
        normalized_stories.append(story)
    return normalized_stories


def verify_and_score_stories():
    stories = Story.objects.prefetch_related("evidence__raw_item__source", "locations").all()
    for story in stories:
        evidence_qs = story.evidence.select_related("raw_item__source")
        distinct_sources = evidence_qs.values_list("raw_item__source_id", flat=True).distinct()
        story.source_count = len(distinct_sources)
        has_official = evidence_qs.filter(raw_item__source__is_official=True).exists()
        if has_official or story.source_count >= 2:
            story.status = Story.Status.VERIFIED
            story.confidence_score = 90 if has_official else 75
        else:
            story.status = Story.Status.UNCONFIRMED
            story.confidence_score = 45
        story.priority_score = score_story(story)
        if story.status == Story.Status.VERIFIED or story.priority_score >= settings.ALERT_DIGEST_THRESHOLD:
            summary, impact, actions = summarize_story(story)
            story.summary = summary
            story.impact_summary = impact
            story.action_summary = actions
            if not story.official_resource_url:
                official_item = evidence_qs.filter(raw_item__source__is_official=True).first()
                if official_item:
                    story.official_resource_url = official_item.raw_item.url
        story.save()


def create_raw_item_from_entry(source, entry):
    url = entry.get("link") or entry.get("id") or source.base_url
    headline = entry.get("title") or "Untitled update"
    body = entry.get("summary") or entry.get("description") or ""
    checksum = compute_checksum(url, headline, body)
    published_at = entry.get("published_parsed")
    published_dt = None
    if published_at:
        published_dt = timezone.datetime(*published_at[:6], tzinfo=timezone.utc)
    return RawIngestItem.objects.get_or_create(
        source=source,
        url=url,
        checksum=checksum,
        defaults={
            "external_id": str(entry.get("id") or ""),
            "headline": headline[:500],
            "raw_body": body,
            "raw_payload": dict(entry),
            "published_at": published_dt,
            "normalized_key": build_normalized_key(headline, body),
        },
    )
