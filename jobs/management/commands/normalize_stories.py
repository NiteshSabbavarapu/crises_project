from django.core.management.base import BaseCommand
from django.utils import timezone

from jobs.models import JobRun
from news.services import normalize_raw_items


class Command(BaseCommand):
    help = "Normalize raw ingest items into canonical stories."

    def handle(self, *args, **options):
        job = JobRun.objects.create(command_name="normalize_stories", status="started")
        try:
            stories = normalize_raw_items()
            job.status = "completed"
            job.details = {"stories_processed": len(stories)}
            self.stdout.write(self.style.SUCCESS(f"Normalized {len(stories)} stories."))
        except Exception as exc:
            job.status = "failed"
            job.details = {"error": str(exc)}
            raise
        finally:
            job.finished_at = timezone.now()
            job.save(update_fields=["status", "details", "finished_at"])
