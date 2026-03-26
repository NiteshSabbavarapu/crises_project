from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import UserLocationPreference
from locations.models import Area, City, Country, State
from news.models import RawIngestItem, Story, StoryLocation
from news.services import build_normalized_key, normalize_raw_items, verify_and_score_stories
from sources.models import Source

User = get_user_model()


class NewsPipelineTests(TestCase):
    def setUp(self):
        self.country = Country.objects.create(name="India", code="IN")
        self.state = State.objects.create(country=self.country, name="Telangana", code="TS")
        self.city = City.objects.create(state=self.state, name="Hyderabad")
        self.area = Area.objects.create(city=self.city, name="Banjara Hills", pincode="500034")
        self.source_1 = Source.objects.create(
            name="The Hindu",
            kind="rss",
            base_url="https://example.com/1",
            feed_url="https://example.com/1/rss",
            credibility_tier="tier_1",
            coverage_scope="national",
        )
        self.source_2 = Source.objects.create(
            name="GHMC",
            kind="rss",
            base_url="https://example.com/2",
            feed_url="https://example.com/2/rss",
            credibility_tier="official",
            coverage_scope="local",
            is_official=True,
        )

    def test_normalization_groups_matching_updates_and_scores_verified_story(self):
        headline = "Flood warning issued for Banjara Hills in Hyderabad"
        key = build_normalized_key(headline, "official flood control advisory")
        RawIngestItem.objects.create(
            source=self.source_1,
            url="https://example.com/a",
            headline=headline,
            raw_body="official flood control advisory",
            raw_payload={},
            published_at=timezone.now(),
            checksum="abc",
            normalized_key=key,
        )
        RawIngestItem.objects.create(
            source=self.source_2,
            url="https://example.com/b",
            headline=headline,
            raw_body="official flood control advisory",
            raw_payload={},
            published_at=timezone.now(),
            checksum="def",
            normalized_key=key,
        )

        stories = normalize_raw_items()
        verify_and_score_stories()

        self.assertEqual(len(stories), 1)
        story = Story.objects.get()
        self.assertEqual(story.status, Story.Status.VERIFIED)
        self.assertGreaterEqual(story.priority_score, 80)
        self.assertTrue(story.locations.filter(area=self.area).exists())


class FakeNewsApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.country = Country.objects.create(name="India", code="IN")
        self.state = State.objects.create(country=self.country, name="Telangana", code="TS")
        self.city = City.objects.create(state=self.state, name="Hyderabad")
        self.area = Area.objects.create(city=self.city, name="Banjara Hills", pincode="500034")
        self.other_city = City.objects.create(state=self.state, name="Warangal")
        self.other_area = Area.objects.create(city=self.other_city, name="Hanamkonda", pincode="506001")
        self.user = User.objects.create_user(
            username="news-user",
            email="news-user@example.com",
            password="VerySecurePass123",
        )
        self.client.force_authenticate(self.user)

    def _create_debunked_story(self, normalized_key, area, city, pincode):
        story = Story.objects.create(
            headline=f"Debunked rumor for {area.name}",
            summary="Rumor disproven.",
            impact_summary="No actual incident.",
            action_summary="Rely on official updates only.",
            category=Story.Category.HEALTH,
            severity=Story.Severity.MEDIUM,
            status=Story.Status.DEBUNKED,
            priority_score=40,
            confidence_score=95,
            source_count=1,
            normalized_key=normalized_key,
            published_at=timezone.now(),
        )
        StoryLocation.objects.create(
            story=story,
            country=self.country,
            state=self.state,
            city=city,
            area=area,
            pincode=pincode,
            relevance_score=80,
        )
        return story

    def test_fake_news_returns_empty_without_primary_location(self):
        self._create_debunked_story("debunked-banjara-hills", self.area, self.city, self.area.pincode)

        response = self.client.get("/api/v1/stories/fake-news")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)
        self.assertEqual(response.data["results"], [])

    def test_fake_news_returns_only_primary_location_matches(self):
        UserLocationPreference.objects.create(
            user=self.user,
            country=self.country,
            state=self.state,
            city=self.city,
            area=self.area,
            pincode=self.area.pincode,
            is_primary=True,
        )
        matching_story = self._create_debunked_story(
            "debunked-banjara-hills", self.area, self.city, self.area.pincode
        )
        self._create_debunked_story(
            "debunked-hanamkonda", self.other_area, self.other_city, self.other_area.pincode
        )

        response = self.client.get("/api/v1/stories/fake-news")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], matching_story.id)
