from django.core.management.base import BaseCommand
from django.utils import timezone

from jobs.models import JobRun
from news.models import Story
from news.services import verify_and_score_stories


class Command(BaseCommand):
    help = "Verify and score normalized stories."

    def handle(self, *args, **options):
        job = JobRun.objects.create(command_name="score_stories", status="started")
        try:
            verify_and_score_stories()
            job.status = "completed"
            job.details = {"stories_scored": Story.objects.count()}
            self.stdout.write(self.style.SUCCESS("Scored stories successfully."))
        except Exception as exc:
            job.status = "failed"
            job.details = {"error": str(exc)}
            raise
        finally:
            job.finished_at = timezone.now()
            job.save(update_fields=["status", "details", "finished_at"])
