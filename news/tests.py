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

    def test_scoring_populates_fallback_fields_for_low_priority_story(self):
        headline = "Routine municipal inspection update in Hyderabad"
        key = build_normalized_key(headline, "inspection notice")
        RawIngestItem.objects.create(
            source=self.source_1,
            url="https://example.com/inspection",
            headline=headline,
            raw_body="inspection notice",
            raw_payload={},
            published_at=timezone.now(),
            checksum="inspection-abc",
            normalized_key=key,
        )

        normalize_raw_items()
        verify_and_score_stories()

        story = Story.objects.get(normalized_key=key)
        self.assertTrue(story.summary)
        self.assertTrue(story.impact_summary)
        self.assertTrue(story.action_summary)


class FakeNewsApiTests(TestCase):
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
            state=city.state,
            city=city,
            area=area,
            pincode=pincode,
            relevance_score=80,
        )
        return story

    def test_fake_news_returns_empty_without_primary_location(self):
        self._create_debunked_story("debunked-banjara-hills", self.area, self.city, self.area.pincode)

        response = self.client.get("/api/v1/stories/fake-news")

        self.assertEqual(response.status_code, 404)

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

    def test_story_list_returns_404_without_primary_location(self):
        response = self.client.get("/api/v1/stories/")

        self.assertEqual(response.status_code, 404)

    def test_complete_news_returns_recent_news_without_location_filter(self):
        older_story = Story.objects.create(
            headline="Older world update",
            summary="Older item",
            impact_summary="Older impact.",
            action_summary="Older action.",
            category=Story.Category.GENERAL,
            severity=Story.Severity.MEDIUM,
            status=Story.Status.UNCONFIRMED,
            priority_score=30,
            confidence_score=40,
            source_count=1,
            normalized_key="older-world-update",
            published_at=timezone.now() - timezone.timedelta(hours=2),
        )
        latest_story = Story.objects.create(
            headline="Latest world update",
            summary="Latest item",
            impact_summary="Latest impact.",
            action_summary="Latest action.",
            category=Story.Category.WEATHER,
            severity=Story.Severity.HIGH,
            status=Story.Status.UNCONFIRMED,
            priority_score=60,
            confidence_score=50,
            source_count=1,
            normalized_key="latest-world-update",
            published_at=timezone.now(),
        )

        response = self.client.get("/api/v1/stories/complete-news")

        self.assertEqual(response.status_code, 200)
        result_ids = [item["id"] for item in response.data["results"]]
        self.assertEqual(result_ids[:2], [latest_story.id, older_story.id])

    def test_complete_news_filters_by_category(self):
        Story.objects.create(
            headline="Weather world update",
            summary="Weather item",
            impact_summary="Weather impact.",
            action_summary="Weather action.",
            category=Story.Category.WEATHER,
            severity=Story.Severity.HIGH,
            status=Story.Status.UNCONFIRMED,
            priority_score=60,
            confidence_score=50,
            source_count=1,
            normalized_key="weather-world-update",
            published_at=timezone.now(),
        )
        Story.objects.create(
            headline="Health world update",
            summary="Health item",
            impact_summary="Health impact.",
            action_summary="Health action.",
            category=Story.Category.HEALTH,
            severity=Story.Severity.MEDIUM,
            status=Story.Status.UNCONFIRMED,
            priority_score=40,
            confidence_score=45,
            source_count=1,
            normalized_key="health-world-update",
            published_at=timezone.now(),
        )

        response = self.client.get("/api/v1/stories/complete-news?category=weather")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["results"])
        self.assertTrue(all(item["category"] == Story.Category.WEATHER for item in response.data["results"]))
