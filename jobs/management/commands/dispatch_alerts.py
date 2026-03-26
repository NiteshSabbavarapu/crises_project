from django.core.management.base import BaseCommand
from django.utils import timezone

from alerts.services import create_and_send_immediate_digests, create_scheduled_digests, evaluate_story_for_users
from jobs.models import JobRun
from news.models import Story


class Command(BaseCommand):
    help = "Evaluate user alert eligibility and send due alerts."

    def handle(self, *args, **options):
        job = JobRun.objects.create(command_name="dispatch_alerts", status="started")
        decisions = 0
        try:
            for story in Story.objects.all():
                decisions += len(evaluate_story_for_users(story))
            create_and_send_immediate_digests()
            create_scheduled_digests()
            job.status = "completed"
            job.details = {"decisions_created": decisions}
            self.stdout.write(self.style.SUCCESS(f"Alert dispatch completed with {decisions} decisions."))
        except Exception as exc:
            job.status = "failed"
            job.details = {"error": str(exc)}
            raise
        finally:
            job.finished_at = timezone.now()
            job.save(update_fields=["status", "details", "finished_at"])
