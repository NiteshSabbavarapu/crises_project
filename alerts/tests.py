from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import UserAlertPreference, UserLocationPreference
from alerts.models import (
    AlertDecision,
    AlertDigest,
    EmailDelivery,
    UserAlertDispatchTracker,
    UserAlertSnapshot,
    UserNewsDelivery,
)
from alerts.services import (
    build_digest_body,
    create_and_send_immediate_digests,
    create_scheduled_digests,
    evaluate_story_for_users,
)
from locations.models import Area, City, Country, State
from news.models import RawIngestItem, Story, StoryLocation, StorySourceEvidence
from sources.models import Source

User = get_user_model()


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AlertDispatchTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.country = Country.objects.create(name="India", code="IN")
        self.state = State.objects.create(country=self.country, name="Telangana", code="TS")
        self.city = City.objects.create(state=self.state, name="Hyderabad")
        self.area = Area.objects.create(city=self.city, name="Banjara Hills", pincode="500034")
        self.other_state = State.objects.create(country=self.country, name="Andhra Pradesh", code="AP")
        self.other_city = City.objects.create(state=self.other_state, name="Warangal")
        self.other_area = Area.objects.create(city=self.other_city, name="Hanamkonda", pincode="506001")
        self.user = User.objects.create_user(
            username="user1", email="user1@example.com", password="VerySecurePass123"
        )
        UserAlertPreference.objects.create(
            user=self.user, frequency=UserAlertPreference.Frequency.CRITICAL_ONLY, categories=[]
        )
        UserLocationPreference.objects.create(
            user=self.user, country=self.country, state=self.state, city=self.city, area=self.area, pincode="500034"
        )
        self.story = Story.objects.create(
            headline="Critical shortage confirmed in Banjara Hills",
            summary="Verified update",
            impact_summary="Short-term supply disruption likely.",
            action_summary="Check official ration updates.",
            category=Story.Category.SUPPLY_CRISIS,
            severity=Story.Severity.CRITICAL,
            status=Story.Status.VERIFIED,
            priority_score=90,
            confidence_score=90,
            source_count=2,
            normalized_key="critical-shortage-banjara-hills",
            official_resource_url="https://example.com/official",
            published_at=timezone.now(),
        )
        StoryLocation.objects.create(
            story=self.story,
            country=self.country,
            state=self.state,
            city=self.city,
            area=self.area,
            pincode="500034",
            relevance_score=80,
        )
        self.global_story = Story.objects.create(
            headline="Major supply disruption reported in Hanamkonda",
            summary="Awareness update",
            impact_summary="Supply chain pressure reported outside your primary area.",
            action_summary="Track verified district updates.",
            category=Story.Category.SUPPLY_CRISIS,
            severity=Story.Severity.CRITICAL,
            status=Story.Status.VERIFIED,
            priority_score=85,
            confidence_score=88,
            source_count=2,
            normalized_key="major-supply-disruption-hanamkonda",
            official_resource_url="https://example.gov/adb14bfd/story-1",
            published_at=timezone.now(),
        )
        StoryLocation.objects.create(
            story=self.global_story,
            country=self.country,
            state=self.other_state,
            city=self.other_city,
            area=self.other_area,
            pincode="506001",
            relevance_score=80,
        )
        self.stale_global_story = Story.objects.create(
            headline="Old flooding advisory reported in Hanamkonda",
            summary="Old awareness update",
            impact_summary="Older advisory outside your primary area.",
            action_summary="Track district updates.",
            category=Story.Category.WEATHER,
            severity=Story.Severity.HIGH,
            status=Story.Status.VERIFIED,
            priority_score=82,
            confidence_score=85,
            source_count=1,
            normalized_key="old-flooding-advisory-hanamkonda",
            official_resource_url="https://example.gov/outdated-story",
            published_at=timezone.now() - timezone.timedelta(hours=13),
        )
        StoryLocation.objects.create(
            story=self.stale_global_story,
            country=self.country,
            state=self.other_state,
            city=self.other_city,
            area=self.other_area,
            pincode="506001",
            relevance_score=70,
        )
        self.official_source = Source.objects.create(
            name="Telangana CMO",
            kind=Source.Kind.RSS,
            base_url="https://cmo.telangana.gov.in",
            feed_url="https://cmo.telangana.gov.in/feed",
            credibility_tier=Source.CredibilityTier.OFFICIAL,
            is_official=True,
            coverage_scope=Source.CoverageScope.STATE,
        )
        self.tier1_source = Source.objects.create(
            name="IMD",
            kind=Source.Kind.RSS,
            base_url="https://imd.gov.in",
            feed_url="https://imd.gov.in/feed",
            credibility_tier=Source.CredibilityTier.TIER_1,
            is_official=False,
            coverage_scope=Source.CoverageScope.NATIONAL,
        )
        self._add_evidence(
            self.story,
            self.official_source,
            "https://cmo.telangana.gov.in/alerts/banjara-hills-shortage",
            "Official shortage alert",
            is_primary=True,
        )
        self._add_evidence(
            self.global_story,
            self.tier1_source,
            "https://imd.gov.in/weather/hanamkonda-rain-alert",
            "IMD rain alert",
            is_primary=True,
        )
        self._add_evidence(
            self.stale_global_story,
            self.tier1_source,
            "https://imd.gov.in/weather/old-hanamkonda-alert",
            "Old IMD alert",
            is_primary=True,
        )
        self.client.force_authenticate(self.user)

    def _add_evidence(self, story, source, url, headline, is_primary=False):
        raw_item = RawIngestItem.objects.create(
            source=source,
            external_id=f"{story.normalized_key}-{headline}",
            url=url,
            headline=headline,
            raw_body=headline,
            raw_payload={},
            published_at=story.published_at,
            checksum=f"{story.normalized_key}-{source.id}-{headline}",
            normalized_key=story.normalized_key,
        )
        StorySourceEvidence.objects.create(story=story, raw_item=raw_item, is_primary=is_primary)
        return raw_item

    def test_critical_story_creates_decision_and_delivery(self):
        decisions = evaluate_story_for_users(self.story)
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].mode, AlertDecision.Mode.IMMEDIATE)

        create_and_send_immediate_digests()

        self.assertEqual(AlertDigest.objects.count(), 1)
        self.assertEqual(EmailDelivery.objects.count(), 1)
        self.assertEqual(EmailDelivery.objects.first().status, EmailDelivery.Status.SENT)

    def test_general_or_low_severity_story_is_not_deliverable(self):
        self.story.category = Story.Category.GENERAL
        self.story.severity = Story.Severity.LOW
        self.story.save(update_fields=["category", "severity"])

        evaluate_story_for_users(self.story)
        create_and_send_immediate_digests()

        self.assertEqual(AlertDigest.objects.count(), 0)

    def test_immediate_digest_groups_local_and_global_and_does_not_resend(self):
        evaluate_story_for_users(self.story)
        evaluate_story_for_users(self.global_story)
        evaluate_story_for_users(self.stale_global_story)

        create_and_send_immediate_digests()

        digest = AlertDigest.objects.get()
        self.assertIn("Local News", digest.body_text)
        self.assertIn("Global News", digest.body_text)
        self.assertIn("https://imd.gov.in/weather/hanamkonda-rain-alert", digest.body_text)
        self.assertNotIn("example.gov", digest.body_text)
        self.assertNotIn("Old flooding advisory reported in Hanamkonda", digest.body_text)
        self.assertEqual(digest.stories.count(), 2)
        self.assertEqual(UserNewsDelivery.objects.filter(user=self.user).count(), 2)
        self.assertEqual(UserAlertSnapshot.objects.filter(user=self.user).count(), 1)

        create_and_send_immediate_digests()

        self.assertEqual(AlertDigest.objects.count(), 1)
        self.assertEqual(EmailDelivery.objects.count(), 1)

    def test_user_news_api_returns_delivered_news(self):
        evaluate_story_for_users(self.story)
        evaluate_story_for_users(self.global_story)
        create_and_send_immediate_digests()

        response = self.client.get("/api/v1/alerts/news")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        scopes = {item["scope"] for item in response.data["results"]}
        self.assertEqual(scopes, {"local", "global"})

    def test_user_without_primary_location_gets_no_delivered_news(self):
        self.user.location_preferences.all().delete()

        evaluate_story_for_users(self.story)
        evaluate_story_for_users(self.global_story)
        create_and_send_immediate_digests()

        response = self.client.get("/api/v1/alerts/news")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)
        self.assertEqual(AlertDigest.objects.count(), 0)
        self.assertEqual(UserNewsDelivery.objects.count(), 0)

    def test_digest_omits_untrusted_story_url_and_prefers_evidence_url(self):
        evaluate_story_for_users(self.global_story)

        create_and_send_immediate_digests()

        digest = AlertDigest.objects.get()
        self.assertIn("https://imd.gov.in/weather/hanamkonda-rain-alert", digest.body_text)
        self.assertNotIn("https://example.gov/adb14bfd/story-1", digest.body_text)

    def test_second_run_sends_when_new_qualifying_story_appears(self):
        evaluate_story_for_users(self.story)
        create_and_send_immediate_digests()

        fresh_global_story = Story.objects.create(
            headline="Fresh rainfall escalation in Hanamkonda",
            summary="New awareness update",
            impact_summary="Stay informed.",
            action_summary="Track official updates.",
            category=Story.Category.WEATHER,
            severity=Story.Severity.HIGH,
            status=Story.Status.VERIFIED,
            priority_score=84,
            confidence_score=86,
            source_count=1,
            normalized_key="fresh-rainfall-escalation-hanamkonda",
            official_resource_url="https://invalid.example.com/new-story",
            published_at=timezone.now(),
        )
        StoryLocation.objects.create(
            story=fresh_global_story,
            country=self.country,
            state=self.other_state,
            city=self.other_city,
            area=self.other_area,
            pincode="506001",
            relevance_score=80,
        )
        self._add_evidence(
            fresh_global_story,
            self.tier1_source,
            "https://imd.gov.in/weather/fresh-hanamkonda-alert",
            "Fresh IMD alert",
            is_primary=True,
        )
        evaluate_story_for_users(fresh_global_story)

        create_and_send_immediate_digests()

        self.assertEqual(AlertDigest.objects.count(), 2)
        self.assertEqual(EmailDelivery.objects.count(), 2)
        latest_digest = AlertDigest.objects.order_by("-created_at").first()
        self.assertIn("https://imd.gov.in/weather/fresh-hanamkonda-alert", latest_digest.body_text)

    def test_scheduled_digest_respects_30_minute_frequency(self):
        self.user.alert_preference.frequency = UserAlertPreference.Frequency.EVERY_30_MIN
        self.user.alert_preference.save(update_fields=["frequency"])
        digest_story = Story.objects.create(
            headline="Digest-level weather update in Banjara Hills",
            summary="Verified update",
            impact_summary="Moderate disruption possible.",
            action_summary="Monitor local advisories.",
            category=Story.Category.WEATHER,
            severity=Story.Severity.HIGH,
            status=Story.Status.VERIFIED,
            priority_score=70,
            confidence_score=88,
            source_count=1,
            normalized_key="digest-level-weather-update-banjara-hills",
            official_resource_url="https://imd.gov.in/weather/banjara-hills-watch",
            published_at=timezone.now(),
        )
        StoryLocation.objects.create(
            story=digest_story,
            country=self.country,
            state=self.state,
            city=self.city,
            area=self.area,
            pincode="500034",
            relevance_score=80,
        )
        self._add_evidence(
            digest_story,
            self.tier1_source,
            "https://imd.gov.in/weather/banjara-hills-watch",
            "IMD watch",
            is_primary=True,
        )

        evaluate_story_for_users(digest_story)
        create_scheduled_digests()
        create_scheduled_digests()

        self.assertEqual(AlertDigest.objects.count(), 1)
        self.assertEqual(EmailDelivery.objects.count(), 1)

    def test_global_news_older_than_12_hours_is_excluded(self):
        self.user.alert_preference.frequency = UserAlertPreference.Frequency.EVERY_30_MIN
        self.user.alert_preference.save(update_fields=["frequency"])
        digest_story = Story.objects.create(
            headline="Older global update in Hanamkonda",
            summary="Awareness update",
            impact_summary="Outside your area.",
            action_summary="Track official updates.",
            category=Story.Category.WEATHER,
            severity=Story.Severity.HIGH,
            status=Story.Status.VERIFIED,
            priority_score=70,
            confidence_score=88,
            source_count=1,
            normalized_key="older-global-update-hanamkonda",
            official_resource_url="https://imd.gov.in/weather/older-hanamkonda-watch",
            published_at=timezone.now() - timezone.timedelta(hours=13),
        )
        StoryLocation.objects.create(
            story=digest_story,
            country=self.country,
            state=self.other_state,
            city=self.other_city,
            area=self.other_area,
            pincode="506001",
            relevance_score=80,
        )
        self._add_evidence(
            digest_story,
            self.tier1_source,
            "https://imd.gov.in/weather/older-hanamkonda-watch",
            "Older IMD watch",
            is_primary=True,
        )

        evaluate_story_for_users(digest_story)
        create_scheduled_digests()

        self.assertEqual(AlertDigest.objects.count(), 0)
        self.assertEqual(EmailDelivery.objects.count(), 0)

    def test_test_digest_body_includes_selected_story_even_if_not_deliverable(self):
        self.story.status = Story.Status.UNCONFIRMED
        self.story.save(update_fields=["status"])

        body = build_digest_body(self.user, [self.story], include_selected_stories=True)

        self.assertIn("Local News", body)
        self.assertIn(self.story.headline, body)
        self.assertNotIn("Local News\nNo new items.", body)
        self.assertNotIn("Global News", body)

    def test_city_level_story_is_local_for_user_with_area_in_same_city(self):
        city_story = Story.objects.create(
            headline="Citywide advisory for Hyderabad",
            summary="Citywide update",
            impact_summary="Stay aware.",
            action_summary="Follow official updates.",
            category=Story.Category.WEATHER,
            severity=Story.Severity.MEDIUM,
            status=Story.Status.UNCONFIRMED,
            priority_score=60,
            confidence_score=50,
            source_count=1,
            normalized_key="citywide-advisory-for-hyderabad",
            published_at=timezone.now(),
        )
        StoryLocation.objects.create(
            story=city_story,
            country=self.country,
            state=self.state,
            city=self.city,
            relevance_score=60,
        )

        body = build_digest_body(self.user, [city_story], include_selected_stories=True)

        self.assertIn("Local News", body)
        self.assertIn(city_story.headline, body)
        self.assertNotIn("Global News\n\nYour Area:", body)

    def test_global_story_uses_awareness_wording_in_digest(self):
        body = build_digest_body(self.user, [self.global_story], include_selected_stories=True)

        self.assertIn("Global News", body)
        self.assertIn("AWARENESS UPDATE", body)
        self.assertIn("outside your state right now", body)
        self.assertIn("Do not assume direct local impact unless your state authorities issue guidance.", body)
        self.assertNotIn("Local News", body)

    def test_empty_global_section_is_omitted_for_local_only_digest(self):
        body = build_digest_body(self.user, [self.story], include_selected_stories=True)

        self.assertIn("Local News", body)
        self.assertNotIn("Global News", body)

    def test_unlocated_crisis_story_can_render_as_global_awareness(self):
        story = Story.objects.create(
            headline="National fuel shortage advisory issued",
            summary="National advisory.",
            impact_summary="Watch for wider supply impact.",
            action_summary="Track official national updates.",
            category=Story.Category.SUPPLY_CRISIS,
            severity=Story.Severity.HIGH,
            status=Story.Status.VERIFIED,
            priority_score=80,
            confidence_score=80,
            source_count=1,
            normalized_key="national-fuel-shortage-advisory-issued",
            published_at=timezone.now(),
        )
        self._add_evidence(
            story,
            self.tier1_source,
            "https://imd.gov.in/weather/national-advisory",
            "National advisory",
            is_primary=True,
        )

        body = build_digest_body(self.user, [story], include_selected_stories=True)

        self.assertIn("Global News", body)
        self.assertIn("AWARENESS UPDATE", body)

    def test_dispatch_tracker_stores_last_fetched_time_and_delivery_response(self):
        story_raw_item = self.story.evidence.select_related("raw_item").first().raw_item
        tracked_fetch_time = timezone.now() - timezone.timedelta(minutes=10)
        story_raw_item.fetched_at = tracked_fetch_time
        story_raw_item.save(update_fields=["fetched_at"])

        evaluate_story_for_users(self.story)
        create_and_send_immediate_digests()

        tracker = UserAlertDispatchTracker.objects.get(user=self.user)
        delivery = EmailDelivery.objects.get()

        self.assertEqual(tracker.last_delivery_id, delivery.id)
        self.assertEqual(tracker.last_delivery_status, EmailDelivery.Status.SENT)
        self.assertEqual(tracker.last_story_fetched_at, tracked_fetch_time)
        self.assertEqual(tracker.last_response_body["recipient"], self.user.email)
        self.assertEqual(tracker.last_response_body["story_ids"], [self.story.id])

    def test_only_stories_fetched_after_tracker_cutoff_are_sent(self):
        first_raw_item = self.story.evidence.select_related("raw_item").first().raw_item
        first_fetch_time = timezone.now() - timezone.timedelta(minutes=20)
        first_raw_item.fetched_at = first_fetch_time
        first_raw_item.save(update_fields=["fetched_at"])

        evaluate_story_for_users(self.story)
        create_and_send_immediate_digests()

        older_story = Story.objects.create(
            headline="Older critical update in Hanamkonda",
            summary="Already old fetch window item.",
            impact_summary="Stay informed.",
            action_summary="Track official updates.",
            category=Story.Category.WEATHER,
            severity=Story.Severity.CRITICAL,
            status=Story.Status.VERIFIED,
            priority_score=85,
            confidence_score=88,
            source_count=1,
            normalized_key="older-critical-update-hanamkonda",
            official_resource_url="https://imd.gov.in/weather/older-critical-hanamkonda",
            published_at=timezone.now(),
        )
        StoryLocation.objects.create(
            story=older_story,
            country=self.country,
            state=self.other_state,
            city=self.other_city,
            area=self.other_area,
            pincode="506001",
            relevance_score=80,
        )
        older_raw_item = self._add_evidence(
            older_story,
            self.tier1_source,
            "https://imd.gov.in/weather/older-critical-hanamkonda",
            "Older critical IMD alert",
            is_primary=True,
        )
        older_raw_item.fetched_at = first_fetch_time - timezone.timedelta(minutes=1)
        older_raw_item.save(update_fields=["fetched_at"])

        newer_story = Story.objects.create(
            headline="New critical update in Hanamkonda",
            summary="Fresh item after tracker cutoff.",
            impact_summary="Stay informed.",
            action_summary="Track official updates.",
            category=Story.Category.WEATHER,
            severity=Story.Severity.CRITICAL,
            status=Story.Status.VERIFIED,
            priority_score=86,
            confidence_score=90,
            source_count=1,
            normalized_key="new-critical-update-hanamkonda",
            official_resource_url="https://imd.gov.in/weather/new-critical-hanamkonda",
            published_at=timezone.now(),
        )
        StoryLocation.objects.create(
            story=newer_story,
            country=self.country,
            state=self.other_state,
            city=self.other_city,
            area=self.other_area,
            pincode="506001",
            relevance_score=80,
        )
        newer_raw_item = self._add_evidence(
            newer_story,
            self.tier1_source,
            "https://imd.gov.in/weather/new-critical-hanamkonda",
            "New critical IMD alert",
            is_primary=True,
        )
        newer_fetch_time = timezone.now() - timezone.timedelta(minutes=5)
        newer_raw_item.fetched_at = newer_fetch_time
        newer_raw_item.save(update_fields=["fetched_at"])

        evaluate_story_for_users(older_story)
        evaluate_story_for_users(newer_story)
        create_and_send_immediate_digests()

        self.assertEqual(AlertDigest.objects.count(), 2)
        latest_digest = AlertDigest.objects.order_by("-created_at").first()
        self.assertEqual(list(latest_digest.stories.values_list("id", flat=True)), [newer_story.id])
