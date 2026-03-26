import hashlib

from django.conf import settings
from django.core.mail import send_mail
from django.utils.html import escape
from django.utils import timezone

from accounts.models import UserAlertPreference
from news.models import Story
from sources.models import Source
from urllib.parse import urlparse

from .models import AlertDecision, AlertDigest, EmailDelivery, UserAlertSnapshot, UserNewsDelivery


def user_matches_story(user, story):
    preferences = user.location_preferences.filter(is_primary=True).first()
    if not preferences or not story.locations.exists():
        return True
    for location in story.locations.all():
        if preferences.area_id and location.area_id == preferences.area_id:
            return True
        if preferences.pincode and location.pincode == preferences.pincode:
            return True
        if not preferences.area_id and preferences.city_id and location.city_id == preferences.city_id:
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


def format_user_area(location):
    if not location:
        return "Unknown area"
    area_name = location.area.name if location.area else location.pincode or "Unknown area"
    city_name = location.city.name if location.city else "Unknown city"
    return f"{area_name}, {city_name}"


def story_affects_user(user, story):
    return user_matches_story(user, story)


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
    return story.status == Story.Status.VERIFIED and has_trusted_story_evidence(story)


def is_story_global_candidate_for_user(user, story, hours=12):
    return is_story_deliverable(story) and not story_affects_user(user, story) and is_story_recent(story, hours=hours)


def build_user_impact_text(user, story):
    area_line = format_user_area(get_user_primary_location(user))
    impact = story.impact_summary or "Potential local impact identified."
    if story_affects_user(user, story):
        return f"For {area_line}: {impact}"
    return (
        f"For {area_line}: this is an awareness news item right now. "
        "No direct impact is currently tagged for your primary area, but you should stay informed."
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


def _coerce_stories(stories):
    if isinstance(stories, Story):
        return [stories]
    return [story for story in stories if story is not None]


def split_stories_for_user(user, stories):
    if not user_has_primary_location(user):
        return [], []
    local_stories = []
    global_stories = []
    for story in _coerce_stories(stories):
        if not is_story_deliverable(story):
            continue
        if story_affects_user(user, story):
            local_stories.append(story)
        elif is_story_global_candidate_for_user(user, story):
            global_stories.append(story)
    return local_stories, global_stories


def filter_deliverable_stories_for_user(user, stories):
    local_stories, global_stories = split_stories_for_user(user, stories)
    return (
        sorted(local_stories, key=lambda story: (-story.priority_score, story.published_at or timezone.now())),
        sorted(global_stories, key=lambda story: (-story.priority_score, story.published_at or timezone.now())),
    )


def _render_story_text_section(user, title, stories):
    if not stories:
        return f"{title}\nNo new items.\n"
    blocks = [build_story_body_text(user, story) for story in stories]
    return f"{title}\n\n" + "\n\n".join(blocks)


def _render_story_html_section(user, title, stories):
    if not stories:
        return (
            f"<section><h2>{escape(title)}</h2>"
            "<p>No new items.</p></section>"
        )
    blocks = "".join(build_story_html(user, story) for story in stories)
    return f"<section><h2>{escape(title)}</h2>{blocks}</section>"


def build_digest_body(user, stories):
    local_stories, global_stories = filter_deliverable_stories_for_user(user, stories)
    header = (
        f"CrisisSync update for {format_user_area(get_user_primary_location(user))}\n"
        f"Generated at: {timezone.localtime(timezone.now()).strftime('%d %b %Y, %I:%M %p')}\n"
    )
    sections = [
        _render_story_text_section(user, "Local News", local_stories),
        _render_story_text_section(user, "Global News", global_stories),
    ]
    return header + "\n\n" + "\n\n".join(sections)


def build_digest_html(user, stories):
    local_stories, global_stories = filter_deliverable_stories_for_user(user, stories)
    return (
        "<div style=\"font-family: Arial, sans-serif; line-height: 1.6; color: #111;\">"
        f"<p><strong>CrisisSync update for:</strong> {escape(format_user_area(get_user_primary_location(user)))}<br>"
        f"<strong>Generated at:</strong> {escape(timezone.localtime(timezone.now()).strftime('%d %b %Y, %I:%M %p'))}</p>"
        f"{_render_story_html_section(user, 'Local News', local_stories)}"
        f"{_render_story_html_section(user, 'Global News', global_stories)}"
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
        send_mail(
            digest.subject,
            digest.body_text,
            settings.DEFAULT_FROM_EMAIL,
            [digest.user.email],
            html_message=digest.body_html or None,
        )
        delivery.status = EmailDelivery.Status.SENT
        delivery.sent_at = timezone.now()
        digest.sent_at = delivery.sent_at
        digest.save(update_fields=["sent_at"])
    except Exception as exc:
        delivery.status = EmailDelivery.Status.FAILED
        delivery.error_message = str(exc)
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
        candidate_stories = list(Story.objects.filter(id__in=story_ids).order_by("-priority_score", "-published_at"))
        unsent_stories = get_unsent_stories_for_user(preference.user, candidate_stories)
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
        decisions = AlertDecision.objects.filter(
            user=preference.user, mode=AlertDecision.Mode.DIGEST, should_send=True
        ).select_related("story")
        unsent_stories = [
            decision.story
            for decision in decisions
        ]
        unsent_stories = get_unsent_stories_for_user(preference.user, unsent_stories)
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
        if delivery.status == EmailDelivery.Status.SENT:
            record_news_deliveries(preference.user, digest, deliverable_stories)
            record_sent_snapshot(preference.user, digest, body_text, story_ids)
