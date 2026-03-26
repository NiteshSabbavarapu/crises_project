from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, MailSettings, SandBoxMode

from accounts.models import UserAlertPreference
from news.models import Story

from .models import AlertDecision, AlertDigest, EmailDelivery


def user_matches_story(user, story):
    preferences = user.location_preferences.filter(is_primary=True).first()
    if not preferences or not story.locations.exists():
        return True
    for location in story.locations.all():
        if preferences.area_id and location.area_id == preferences.area_id:
            return True
        if preferences.city_id and location.city_id == preferences.city_id:
            return True
        if preferences.pincode and location.pincode == preferences.pincode:
            return True
    return False


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


def build_digest_body(user, story):
    location = user.location_preferences.filter(is_primary=True).first()
    area_line = "Unknown area"
    if location:
        area_name = location.area.name if location.area else location.pincode or "Unknown area"
        city_name = location.city.name if location.city else "Unknown city"
        area_line = f"{area_name}, {city_name}"
    summary = story.summary or story.headline
    impact = story.impact_summary or "Potential local impact identified."
    actions = story.action_summary or "Follow official guidance and avoid forwarding unverified updates."
    return (
        f"Your Area: {area_line}\n"
        f"Last updated: {timezone.localtime(timezone.now()).strftime('%d %b %Y, %I:%M %p')}\n\n"
        f"TOP ALERT\n{story.headline}\n"
        f"Status: {story.status}\n"
        f"Summary: {summary}\n"
        f"What this means for you: {impact}\n"
        f"Your action steps:\n{actions}\n"
        f"Official resource: {story.official_resource_url or 'Not available'}\n"
    )


def send_via_sendgrid(to_email, subject, body_text):
    message = Mail(
        from_email=settings.DEFAULT_FROM_EMAIL,
        to_emails=to_email,
        subject=subject,
        plain_text_content=body_text,
    )
    if settings.SENDGRID_SANDBOX_MODE:
        message.mail_settings = MailSettings(sandbox_mode=SandBoxMode(True))
    client = SendGridAPIClient(settings.SENDGRID_API_KEY)
    return client.send(message)


def send_digest(digest):
    delivery = EmailDelivery.objects.create(
        user=digest.user,
        digest=digest,
        subject=digest.subject,
        status=EmailDelivery.Status.PENDING,
    )
    try:
        provider = getattr(settings, "EMAIL_DELIVERY_PROVIDER", "smtp").lower()
        if provider == "sendgrid":
            if not settings.SENDGRID_API_KEY:
                raise ValueError("EMAIL_DELIVERY_PROVIDER is sendgrid but SENDGRID_API_KEY is missing.")
            response = send_via_sendgrid(digest.user.email, digest.subject, digest.body_text)
            delivery.provider_message_id = response.headers.get("X-Message-Id", "")
            delivery.response_body = {"status_code": response.status_code}
        else:
            send_mail(digest.subject, digest.body_text, settings.DEFAULT_FROM_EMAIL, [digest.user.email])
        delivery.status = EmailDelivery.Status.SENT
        delivery.sent_at = timezone.now()
        digest.sent_at = delivery.sent_at
        digest.save(update_fields=["sent_at"])
    except Exception as exc:
        delivery.status = EmailDelivery.Status.FAILED
        delivery.error_message = str(exc)
    delivery.save()
    return delivery


def evaluate_story_for_users(story):
    created = []
    for preference in UserAlertPreference.objects.select_related("user").all():
        if not preference.email_enabled or not preference.user.email:
            continue
        if preference.categories and story.category not in preference.categories:
            continue
        if not user_matches_story(preference.user, story):
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
    stories = Story.objects.filter(status=Story.Status.VERIFIED, priority_score__gte=settings.ALERT_IMMEDIATE_THRESHOLD)
    for story in stories:
        for decision in AlertDecision.objects.filter(story=story, mode=AlertDecision.Mode.IMMEDIATE, should_send=True):
            if AlertDigest.objects.filter(user=decision.user, stories=story, digest_type=AlertDigest.DigestType.IMMEDIATE).exists():
                continue
            digest = AlertDigest.objects.create(
                user=decision.user,
                digest_type=AlertDigest.DigestType.IMMEDIATE,
                subject=build_digest_subject(story, AlertDigest.DigestType.IMMEDIATE),
                body_text=build_digest_body(decision.user, story),
                scheduled_for=timezone.now(),
            )
            digest.stories.add(story)
            send_digest(digest)


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
            if not AlertDigest.objects.filter(
                user=preference.user, stories=decision.story, digest_type=AlertDigest.DigestType.SCHEDULED
            ).exists()
        ]
        if not unsent_stories:
            continue
        subject = f"[DIGEST] {len(unsent_stories)} verified CrisisSync updates"
        body = "\n\n".join(build_digest_body(preference.user, story) for story in unsent_stories[:5])
        digest = AlertDigest.objects.create(
            user=preference.user,
            digest_type=AlertDigest.DigestType.SCHEDULED,
            subject=subject,
            body_text=body,
            scheduled_for=timezone.now(),
        )
        digest.stories.add(*unsent_stories)
        send_digest(digest)
