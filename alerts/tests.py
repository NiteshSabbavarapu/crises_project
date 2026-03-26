from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import UserAlertPreference, UserLocationPreference
from alerts.models import AlertDecision, AlertDigest, EmailDelivery
from alerts.services import create_and_send_immediate_digests, evaluate_story_for_users
from locations.models import Area, City, Country, State
from news.models import Story, StoryLocation

User = get_user_model()


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AlertDispatchTests(TestCase):
    def setUp(self):
        self.country = Country.objects.create(name="India", code="IN")
        self.state = State.objects.create(country=self.country, name="Telangana", code="TS")
        self.city = City.objects.create(state=self.state, name="Hyderabad")
        self.area = Area.objects.create(city=self.city, name="Banjara Hills", pincode="500034")
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

    def test_critical_story_creates_decision_and_delivery(self):
        decisions = evaluate_story_for_users(self.story)
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].mode, AlertDecision.Mode.IMMEDIATE)

        create_and_send_immediate_digests()

        self.assertEqual(AlertDigest.objects.count(), 1)
        self.assertEqual(EmailDelivery.objects.count(), 1)
        self.assertEqual(EmailDelivery.objects.first().status, EmailDelivery.Status.SENT)
