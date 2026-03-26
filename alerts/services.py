import hashlib

from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Max
from django.utils.html import escape
from django.utils import timezone

from accounts.models import UserAlertPreference
from news.models import Story
from sources.models import Source
from urllib.parse import urlparse

from .models import (
    AlertDecision,
    AlertDigest,
    EmailDelivery,
    UserAlertDispatchTracker,
    UserAlertSnapshot,
    UserNewsDelivery,
)

CRISIS_CATEGORIES = {
    Story.Category.SUPPLY_CRISIS,
    Story.Category.WEATHER,
    Story.Category.CIVIL_UNREST,
    Story.Category.PRICE_SURGE,
    Story.Category.HEALTH,
}


def is_crisis_story(story):
    return story.category in CRISIS_CATEGORIES and story.severity != Story.Severity.LOW


def user_matches_story(user, story):
    preferences = user.location_preferences.filter(is_primary=True).first()
    if not preferences:
        return True
    if not story.locations.exists():
        return False
    for location in story.locations.all():
        if preferences.state_id and location.state_id == preferences.state_id:
            return True
        if preferences.area_id and location.area_id == preferences.area_id:
            return True
        if preferences.pincode and location.pincode == preferences.pincode:
            return True
        if preferences.city_id and location.city_id == preferences.city_id:
            return True
    return False


def story_scope_for_user(user, story):
    return UserNewsDelivery.Scope.LOCAL if user_matches_story(user, story) else UserNewsDelivery.Scope.GLOBAL


def story_delivery_mode(story, preference):
    if story.priority_score >= settings.ALERT_IMMEDIATE_THRESHOLD:
        return AlertDecision.Mode.IMMEDIATE
    if story.priority_score >= settings.ALERT_DIGEST_THRESHOLD:
        if preference.frequency == UserAlertPreference.Frequency.CRITICAL_ONLY:
            return AlertDecision.Mode.SKIPPED
        return AlertDecision.Mode.DIGEST
    return AlertDecision.Mode.DASHBOARD_ONLY


def build_digest_subject(story, digest_type):
    prefix = "[CRITICAL]" if digest_type == AlertDigest.DigestType.IMMEDIATE else "[DIGEST]"
    return f"{prefix} {story.headline[:200]}"


def build_digest_subject_for_stories(stories, digest_type):
    stories = list(stories)
    if not stories:
        prefix = "[CRITICAL]" if digest_type == AlertDigest.DigestType.IMMEDIATE else "[DIGEST]"
        return f"{prefix} CrisisSync update"
    if len(stories) == 1:
        return build_digest_subject(stories[0], digest_type)
    prefix = "[CRITICAL]" if digest_type == AlertDigest.DigestType.IMMEDIATE else "[DIGEST]"
    return f"{prefix} {len(stories)} new CrisisSync updates"


def get_user_primary_location(user):
    return user.location_preferences.filter(is_primary=True).first()


def user_has_primary_location(user):
    return get_user_primary_location(user) is not None


def get_user_primary_state_id(user):
    location = get_user_primary_location(user)
    return location.state_id if location else None


def format_user_area(location):
    if not location:
        return "Unknown area"
    area_name = location.area.name if location.area else location.pincode or "Unknown area"
    city_name = location.city.name if location.city else "Unknown city"
    return f"{area_name}, {city_name}"


def story_affects_user(user, story):
    return user_matches_story(user, story)


def story_is_global_for_user(user, story):
    user_state_id = get_user_primary_state_id(user)
    if not user_state_id:
        return False
    if not story.locations.exists():
        return is_crisis_story(story)
    story_state_ids = {location.state_id for location in story.locations.all() if location.state_id}
    if not story_state_ids:
        return is_crisis_story(story)
    return user_state_id not in story_state_ids


def normalize_resource_url(url):
    value = (url or "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme:
        return value
    return f"https://{value.lstrip('/')}"


def is_trusted_source(source):
    if not source or not source.is_active:
        return False
    return source.is_official or source.credibility_tier in {
        Source.CredibilityTier.OFFICIAL,
        Source.CredibilityTier.TIER_1,
    }


def _host_matches_trusted_source(host, source):
    base_host = (urlparse(source.base_url).netloc or "").lower()
    if not base_host:
        return False
    return host == base_host or host.endswith(f".{base_host}") or base_host.endswith(f".{host}")


def is_trusted_url(url):
    normalized = normalize_resource_url(url)
    parsed = urlparse(normalized)
    host = (parsed.netloc or "").lower()
    if not host:
        return False
    if any(
        host == domain or host.endswith(f".{domain}")
        for domain in ("gov.in", "nic.in", "ndma.gov.in", "imd.gov.in", "mohfw.gov.in")
    ):
        return True
    trusted_sources = Source.objects.filter(is_active=True).exclude(base_url="")
    for source in trusted_sources:
        if is_trusted_source(source) and _host_matches_trusted_source(host, source):
            return True
    return False


def get_story_trusted_evidence(story):
    evidence = list(
        story.evidence.select_related("raw_item__source").all()
    )
    trusted = [item for item in evidence if is_trusted_source(item.raw_item.source)]
    return sorted(
        trusted,
        key=lambda item: (
            not item.raw_item.source.is_official,
            not item.is_primary,
            -(item.raw_item.published_at or item.raw_item.fetched_at).timestamp(),
        ),
    )


def get_story_official_resource(story):
    for evidence in get_story_trusted_evidence(story):
        if evidence.raw_item.source.is_official and is_trusted_url(evidence.raw_item.url):
            return normalize_resource_url(evidence.raw_item.url)
    for evidence in get_story_trusted_evidence(story):
        if is_trusted_url(evidence.raw_item.url):
            return normalize_resource_url(evidence.raw_item.url)
    if story.official_resource_url and is_trusted_url(story.official_resource_url):
        return normalize_resource_url(story.official_resource_url)
    return ""


def has_trusted_story_evidence(story):
    return bool(get_story_trusted_evidence(story))


def get_recent_cutoff(hours=12):
    return timezone.now() - timezone.timedelta(hours=hours)


def is_story_recent(story, hours=12):
    if not story.published_at:
        return False
    return story.published_at >= get_recent_cutoff(hours=hours)


def is_story_deliverable(story):
    return is_crisis_story(story) and story.status == Story.Status.VERIFIED and has_trusted_story_evidence(story)


def is_story_global_candidate_for_user(user, story, hours=12):
    min_priority = max(int(getattr(settings, "ALERT_DIGEST_THRESHOLD", 50) or 50), 1)
    return (
        is_story_deliverable(story)
        and story_is_global_for_user(user, story)
        and is_story_recent(story, hours=hours)
        and story.priority_score >= min_priority
    )


def get_global_news_window_hours():
    return max(int(getattr(settings, "GLOBAL_NEWS_WINDOW_HOURS", 12) or 12), 1)


def get_scheduled_digest_interval(preference):
    if preference.frequency == UserAlertPreference.Frequency.EVERY_30_MIN:
        return timezone.timedelta(minutes=30)
    if preference.frequency == UserAlertPreference.Frequency.HOURLY:
        return timezone.timedelta(hours=1)
    return None


def is_scheduled_digest_due(user, preference):
    interval = get_scheduled_digest_interval(preference)
    if interval is None:
        return False
    last_digest = (
        AlertDigest.objects.filter(user=user, digest_type=AlertDigest.DigestType.SCHEDULED)
        .exclude(sent_at__isnull=True)
        .order_by("-sent_at")
        .first()
    )
    if not last_digest:
        return True
    return timezone.now() >= last_digest.sent_at + interval


def build_user_impact_text(user, story):
    area_line = format_user_area(get_user_primary_location(user))
    impact = story.impact_summary or "Potential local impact identified."
    if story_affects_user(user, story):
        return f"For {area_line}: {impact}"
    return (
        f"For {area_line}: this is an awareness news item right now. "
        "No direct impact is currently tagged for your primary area, but you should stay informed."
    )


def build_global_impact_text(user, story):
    area_line = format_user_area(get_user_primary_location(user))
    return (
        f"For {area_line}: this update is outside your state right now. "
        "It matters for broader awareness and may affect travel, supply, policy, or connected regions if the situation expands."
    )


def build_action_text(user, story):
    actions = story.action_summary or "Follow official guidance and avoid forwarding unverified updates."
    if story_affects_user(user, story):
        return actions
    return (
        "- Stay aware and monitor official updates for escalation.\n"
        "- Avoid forwarding unverified local impact claims.\n"
        "- Review the official resource if this situation moves closer to your area."
    )


def build_global_action_text(user, story):
    return (
        "- Stay aware and monitor official updates for escalation.\n"
        "- Do not assume direct local impact unless your state authorities issue guidance.\n"
        "- Review the official resource if this situation expands or affects connected regions."
    )


def build_story_body_text(user, story):
    location = user.location_preferences.filter(is_primary=True).first()
    area_line = format_user_area(location)
    summary = story.summary or story.headline
    impact = build_user_impact_text(user, story)
    actions = build_action_text(user, story)
    alert_label = "TOP ALERT" if story_affects_user(user, story) else "AWARENESS NEWS"
    body = (
        f"Your Area: {area_line}\n"
        f"Last updated: {timezone.localtime(timezone.now()).strftime('%d %b %Y, %I:%M %p')}\n\n"
        f"{alert_label}\n"
        f"{story.headline}\n\n"
        f"Status: {story.status}\n"
        f"News: {summary}\n"
        f"What this means for you: {impact}\n"
        f"What you should do:\n{actions}\n"
    )
    official_resource = get_story_official_resource(story)
    if official_resource:
        body += f"Official resource: {official_resource}\n"
    return body


def build_global_story_body_text(user, story):
    area_line = format_user_area(get_user_primary_location(user))
    summary = story.summary or story.headline
    impact = build_global_impact_text(user, story)
    actions = build_global_action_text(user, story)
    body = (
        f"Your Area: {area_line}\n"
        f"Last updated: {timezone.localtime(timezone.now()).strftime('%d %b %Y, %I:%M %p')}\n\n"
        "AWARENESS UPDATE\n"
        f"{story.headline}\n\n"
        f"Status: {story.status}\n"
        f"News: {summary}\n"
        f"What this means for you: {impact}\n"
        f"What you should do:\n{actions}\n"
    )
    official_resource = get_story_official_resource(story)
    if official_resource:
        body += f"Official resource: {official_resource}\n"
    return body


def build_story_html(user, story):
    area_line = format_user_area(get_user_primary_location(user))
    headline = escape(story.headline)
    summary = escape(story.summary or story.headline)
    impact = escape(build_user_impact_text(user, story))
    actions = build_action_text(user, story)
    action_lines = [line.lstrip("- ").strip() for line in actions.splitlines() if line.strip()]
    action_html = "".join(f"<li>{escape(line)}</li>" for line in action_lines)
    label = "Top Alert" if story_affects_user(user, story) else "Awareness News"
    official_url = get_story_official_resource(story)
    html = (
        "<div style=\"font-family: Arial, sans-serif; line-height: 1.6; color: #111;\">"
        f"<p><strong>Your area:</strong> {escape(area_line)}<br>"
        f"<strong>Last updated:</strong> {escape(timezone.localtime(timezone.now()).strftime('%d %b %Y, %I:%M %p'))}</p>"
        f"<p><strong>{escape(label)}</strong></p>"
        f"<p><strong>{headline}</strong></p>"
        f"<p><strong>News:</strong> {summary}</p>"
        f"<p><strong>What this means for you:</strong> {impact}</p>"
        f"<p><strong>What you should do:</strong></p><ul>{action_html}</ul>"
        "</div>"
    )
    if official_url:
        official_html = (
            f'<a href="{escape(official_url)}" target="_blank" rel="noopener noreferrer">{escape(official_url)}</a>'
        )
        html = html.replace(
            "</div>", f"<p><strong>Official resource:</strong> {official_html}</p></div>", 1
        )
    return html


def build_global_story_html(user, story):
    area_line = format_user_area(get_user_primary_location(user))
    headline = escape(story.headline)
    summary = escape(story.summary or story.headline)
    impact = escape(build_global_impact_text(user, story))
    actions = build_global_action_text(user, story)
    action_lines = [line.lstrip("- ").strip() for line in actions.splitlines() if line.strip()]
    action_html = "".join(f"<li>{escape(line)}</li>" for line in action_lines)
    official_url = get_story_official_resource(story)
    html = (
        "<div style=\"font-family: Arial, sans-serif; line-height: 1.6; color: #111;\">"
        f"<p><strong>Your area:</strong> {escape(area_line)}<br>"
        f"<strong>Last updated:</strong> {escape(timezone.localtime(timezone.now()).strftime('%d %b %Y, %I:%M %p'))}</p>"
        "<p><strong>Awareness Update</strong></p>"
        f"<p><strong>{headline}</strong></p>"
        f"<p><strong>News:</strong> {summary}</p>"
        f"<p><strong>What this means for you:</strong> {impact}</p>"
        f"<p><strong>What you should do:</strong></p><ul>{action_html}</ul>"
        "</div>"
    )
    if official_url:
        official_html = (
            f'<a href="{escape(official_url)}" target="_blank" rel="noopener noreferrer">{escape(official_url)}</a>'
        )
        html = html.replace(
            "</div>", f"<p><strong>Official resource:</strong> {official_html}</p></div>", 1
        )
    return html


def _coerce_stories(stories):
    if isinstance(stories, Story):
        return [stories]
    return [story for story in stories if story is not None]


def split_stories_for_user(user, stories):
    if not user_has_primary_location(user):
        return [], []
    local_stories = []
    global_stories = []
    global_news_window_hours = get_global_news_window_hours()
    for story in _coerce_stories(stories):
        if not is_story_deliverable(story):
            continue
        if story_affects_user(user, story):
            local_stories.append(story)
        elif is_story_global_candidate_for_user(user, story, hours=global_news_window_hours):
            global_stories.append(story)
    return local_stories, global_stories


def split_selected_stories_for_user(user, stories):
    if not user_has_primary_location(user):
        return [], []
    local_stories = []
    global_stories = []
    for story in _coerce_stories(stories):
        if story_affects_user(user, story):
            local_stories.append(story)
        else:
            global_stories.append(story)
    return local_stories, global_stories


def filter_deliverable_stories_for_user(user, stories):
    local_stories, global_stories = split_stories_for_user(user, stories)
    return (
        sorted(local_stories, key=lambda story: (-story.priority_score, story.published_at or timezone.now())),
        sorted(global_stories, key=lambda story: (-story.priority_score, story.published_at or timezone.now())),
    )


def _render_story_text_section(user, title, stories, renderer):
    if not stories:
        return ""
    blocks = [renderer(user, story) for story in stories]
    return f"{title}\n\n" + "\n\n".join(blocks)


def _render_story_html_section(user, title, stories, renderer):
    if not stories:
        return ""
    blocks = "".join(renderer(user, story) for story in stories)
    return f"<section><h2>{escape(title)}</h2>{blocks}</section>"


def build_digest_body(user, stories, include_selected_stories=False):
    if include_selected_stories:
        local_stories, global_stories = split_selected_stories_for_user(user, stories)
    else:
        local_stories, global_stories = filter_deliverable_stories_for_user(user, stories)
    header = (
        f"CrisisSync update for {format_user_area(get_user_primary_location(user))}\n"
        f"Generated at: {timezone.localtime(timezone.now()).strftime('%d %b %Y, %I:%M %p')}\n"
    )
    sections = []
    local_section = _render_story_text_section(user, "Local News", local_stories, build_story_body_text)
    global_section = _render_story_text_section(user, "Global News", global_stories, build_global_story_body_text)
    if local_section:
        sections.append(local_section)
    if global_section:
        sections.append(global_section)
    if not sections:
        sections.append("No new items.")
    return header + "\n\n" + "\n\n".join(sections)


def build_digest_html(user, stories, include_selected_stories=False):
    if include_selected_stories:
        local_stories, global_stories = split_selected_stories_for_user(user, stories)
    else:
        local_stories, global_stories = filter_deliverable_stories_for_user(user, stories)
    local_section = _render_story_html_section(user, "Local News", local_stories, build_story_html)
    global_section = _render_story_html_section(user, "Global News", global_stories, build_global_story_html)
    sections = "".join(section for section in (local_section, global_section) if section)
    if not sections:
        sections = "<section><p>No new items.</p></section>"
    return (
        "<div style=\"font-family: Arial, sans-serif; line-height: 1.6; color: #111;\">"
        f"<p><strong>CrisisSync update for:</strong> {escape(format_user_area(get_user_primary_location(user)))}<br>"
        f"<strong>Generated at:</strong> {escape(timezone.localtime(timezone.now()).strftime('%d %b %Y, %I:%M %p'))}</p>"
        f"{sections}"
        "</div>"
    )


def send_digest(digest):
    delivery = EmailDelivery.objects.create(
        user=digest.user,
        digest=digest,
        subject=digest.subject,
        status=EmailDelivery.Status.PENDING,
    )
    try:
        sent_count = send_mail(
            digest.subject,
            digest.body_text,
            settings.DEFAULT_FROM_EMAIL,
            [digest.user.email],
            html_message=digest.body_html or None,
        )
        delivery.status = EmailDelivery.Status.SENT
        delivery.sent_at = timezone.now()
        delivery.response_body = {
            "channel": "email",
            "recipient": digest.user.email,
            "sent_count": sent_count,
            "digest_id": digest.id,
            "story_ids": list(digest.stories.values_list("id", flat=True)),
            "sent_at": timezone.localtime(delivery.sent_at).isoformat(),
        }
        digest.sent_at = delivery.sent_at
        digest.save(update_fields=["sent_at"])
    except Exception as exc:
        delivery.status = EmailDelivery.Status.FAILED
        delivery.error_message = str(exc)
        delivery.response_body = {
            "channel": "email",
            "recipient": digest.user.email,
            "digest_id": digest.id,
            "story_ids": list(digest.stories.values_list("id", flat=True)),
            "error": str(exc),
        }
    delivery.save()
    return delivery


def build_message_content_hash(body_text):
    normalized_lines = []
    for line in body_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("Generated at:") or stripped.startswith("Last updated:"):
            continue
        normalized_lines.append(stripped)
    normalized = "\n".join(line for line in normalized_lines if line)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def get_last_sent_snapshot(user, channel="email"):
    return (
        UserAlertSnapshot.objects.filter(user=user, channel=channel)
        .order_by("-sent_at")
        .first()
    )


def should_send_message(user, body_text, story_ids, channel="email"):
    story_ids = sorted(set(story_ids))
    if not story_ids:
        return False
    content_hash = build_message_content_hash(body_text)
    last_snapshot = get_last_sent_snapshot(user, channel=channel)
    if not last_snapshot:
        return True
    previous_story_ids = sorted(set(last_snapshot.story_ids or []))
    if previous_story_ids == story_ids:
        return False
    if last_snapshot.content_hash == content_hash:
        return False
    return bool(set(story_ids) - set(previous_story_ids))


def record_sent_snapshot(user, digest, body_text, story_ids, channel="email"):
    UserAlertSnapshot.objects.create(
        user=user,
        digest=digest,
        channel=channel,
        content_hash=build_message_content_hash(body_text),
        body_text=body_text,
        story_ids=sorted(set(story_ids)),
    )


def get_unsent_stories_for_user(user, stories):
    stories = _coerce_stories(stories)
    if not stories:
        return []
    sent_story_ids = set(
        UserNewsDelivery.objects.filter(user=user, story__in=stories).values_list("story_id", flat=True)
    )
    return [story for story in stories if story.id not in sent_story_ids]


def get_user_dispatch_tracker(user, channel="email"):
    tracker, _ = UserAlertDispatchTracker.objects.get_or_create(user=user, defaults={"channel": channel})
    if tracker.channel != channel:
        tracker.channel = channel
        tracker.save(update_fields=["channel"])
    return tracker


def get_story_latest_fetched_at(story):
    value = getattr(story, "latest_fetched_at", None)
    if value:
        return value
    return story.evidence.aggregate(latest=Max("raw_item__fetched_at"))["latest"]


def filter_stories_after_tracker(user, stories, channel="email"):
    tracker = get_user_dispatch_tracker(user, channel=channel)
    if not tracker.last_story_fetched_at:
        return list(stories)
    filtered = []
    for story in _coerce_stories(stories):
        latest_fetched_at = get_story_latest_fetched_at(story)
        if latest_fetched_at and latest_fetched_at > tracker.last_story_fetched_at:
            filtered.append(story)
    return filtered


def update_dispatch_tracker(user, delivery, stories, digest=None, channel="email"):
    tracker = get_user_dispatch_tracker(user, channel=channel)
    tracker.last_checked_at = timezone.now()
    tracker.last_digest = digest
    tracker.last_delivery = delivery
    tracker.last_delivery_status = delivery.status
    tracker.last_response_body = delivery.response_body or {}
    tracker.last_error_message = delivery.error_message or ""
    if delivery.status == EmailDelivery.Status.SENT:
        tracker.last_sent_at = delivery.sent_at
        latest_fetched_times = [
            latest_fetched_at
            for latest_fetched_at in (get_story_latest_fetched_at(story) for story in _coerce_stories(stories))
            if latest_fetched_at is not None
        ]
        if latest_fetched_times:
            tracker.last_story_fetched_at = max(latest_fetched_times)
    tracker.save()


def record_news_deliveries(user, digest, stories):
    for story in _coerce_stories(stories):
        UserNewsDelivery.objects.get_or_create(
            user=user,
            story=story,
            defaults={
                "digest": digest,
                "scope": story_scope_for_user(user, story),
            },
        )


def evaluate_story_for_users(story):
    created = []
    for preference in UserAlertPreference.objects.select_related("user").all():
        if not preference.email_enabled or not preference.user.email:
            continue
        if preference.categories and story.category not in preference.categories:
            continue
        mode = story_delivery_mode(story, preference)
        should_send = mode in {AlertDecision.Mode.IMMEDIATE, AlertDecision.Mode.DIGEST}
        decision, _ = AlertDecision.objects.update_or_create(
            user=preference.user,
            story=story,
            mode=mode,
            defaults={
                "should_send": should_send,
                "score_snapshot": story.priority_score,
                "reasons": {"category": story.category, "priority_score": story.priority_score},
            },
        )
        created.append(decision)
    return created


def create_and_send_immediate_digests():
    for preference in UserAlertPreference.objects.select_related("user").all():
        story_ids = AlertDecision.objects.filter(
            user=preference.user,
            mode=AlertDecision.Mode.IMMEDIATE,
            should_send=True,
            story__status=Story.Status.VERIFIED,
            story__priority_score__gte=settings.ALERT_IMMEDIATE_THRESHOLD,
        ).values_list("story_id", flat=True)
        candidate_stories = list(
            Story.objects.filter(id__in=story_ids)
            .annotate(latest_fetched_at=Max("evidence__raw_item__fetched_at"))
            .order_by("-priority_score", "-published_at")
        )
        unsent_stories = get_unsent_stories_for_user(preference.user, candidate_stories)
        unsent_stories = filter_stories_after_tracker(preference.user, unsent_stories)
        local_stories, global_stories = filter_deliverable_stories_for_user(preference.user, unsent_stories)
        deliverable_stories = [*local_stories, *global_stories]
        if not deliverable_stories:
            continue
        body_text = build_digest_body(preference.user, deliverable_stories)
        story_ids = [story.id for story in deliverable_stories]
        if not should_send_message(preference.user, body_text, story_ids):
            continue
        digest = AlertDigest.objects.create(
            user=preference.user,
            digest_type=AlertDigest.DigestType.IMMEDIATE,
            subject=build_digest_subject_for_stories(deliverable_stories, AlertDigest.DigestType.IMMEDIATE),
            body_text=body_text,
            body_html=build_digest_html(preference.user, deliverable_stories),
            scheduled_for=timezone.now(),
        )
        digest.stories.add(*deliverable_stories)
        delivery = send_digest(digest)
        update_dispatch_tracker(preference.user, delivery, deliverable_stories, digest=digest)
        if delivery.status == EmailDelivery.Status.SENT:
            record_news_deliveries(preference.user, digest, deliverable_stories)
            record_sent_snapshot(preference.user, digest, body_text, story_ids)


def create_scheduled_digests():
    for preference in UserAlertPreference.objects.select_related("user").all():
        if preference.frequency not in {
            UserAlertPreference.Frequency.EVERY_30_MIN,
            UserAlertPreference.Frequency.HOURLY,
        }:
            continue
        if not is_scheduled_digest_due(preference.user, preference):
            continue
        decisions = AlertDecision.objects.filter(
            user=preference.user, mode=AlertDecision.Mode.DIGEST, should_send=True
        ).select_related("story")
        unsent_stories = [
            decision.story
            for decision in decisions
        ]
        unsent_stories = get_unsent_stories_for_user(preference.user, unsent_stories)
        unsent_stories = filter_stories_after_tracker(preference.user, unsent_stories)
        local_stories, global_stories = filter_deliverable_stories_for_user(preference.user, unsent_stories)
        deliverable_stories = [*(local_stories[:5]), *(global_stories[:5])]
        if not deliverable_stories:
            continue
        deliverable_stories = deliverable_stories[:5]
        body_text = build_digest_body(preference.user, deliverable_stories)
        story_ids = [story.id for story in deliverable_stories]
        if not should_send_message(preference.user, body_text, story_ids):
            continue
        digest = AlertDigest.objects.create(
            user=preference.user,
            digest_type=AlertDigest.DigestType.SCHEDULED,
            subject=build_digest_subject_for_stories(deliverable_stories, AlertDigest.DigestType.SCHEDULED),
            body_text=body_text,
            body_html=build_digest_html(preference.user, deliverable_stories),
            scheduled_for=timezone.now(),
        )
        digest.stories.add(*deliverable_stories)
        delivery = send_digest(digest)
        update_dispatch_tracker(preference.user, delivery, deliverable_stories, digest=digest)
        if delivery.status == EmailDelivery.Status.SENT:
            record_news_deliveries(preference.user, digest, deliverable_stories)
            record_sent_snapshot(preference.user, digest, body_text, story_ids)
