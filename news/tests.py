from django.test import TestCase
from django.utils import timezone

from locations.models import Area, City, Country, State
from news.models import RawIngestItem, Story
from news.services import build_normalized_key, normalize_raw_items, verify_and_score_stories
from sources.models import Source


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
