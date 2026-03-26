from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import UserAlertPreference, UserLocationPreference
from alerts.models import AlertDecision, AlertDigest, EmailDelivery, UserAlertSnapshot, UserNewsDelivery
from alerts.services import create_and_send_immediate_digests, evaluate_story_for_users
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
        self.other_city = City.objects.create(state=self.state, name="Warangal")
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
            state=self.state,
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
            state=self.state,
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

    def test_critical_story_creates_decision_and_delivery(self):
        decisions = evaluate_story_for_users(self.story)
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].mode, AlertDecision.Mode.IMMEDIATE)

        create_and_send_immediate_digests()

        self.assertEqual(AlertDigest.objects.count(), 1)
        self.assertEqual(EmailDelivery.objects.count(), 1)
        self.assertEqual(EmailDelivery.objects.first().status, EmailDelivery.Status.SENT)

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
            state=self.state,
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
