import feedparser
import requests
from django.core.management.base import BaseCommand
from django.utils import timezone

from jobs.models import JobRun
from news.services import create_raw_item_from_entry
from sources.models import Source


class Command(BaseCommand):
    help = "Fetch active crisis news sources and persist raw ingest items."

    def handle(self, *args, **options):
        job = JobRun.objects.create(command_name="ingest_sources", status="started")
        created_count = 0
        failures = {}
        try:
            for source in Source.objects.filter(is_active=True):
                if source.kind != Source.Kind.RSS or not source.feed_url:
                    continue
                try:
                    response = requests.get(source.feed_url, timeout=20, headers={"User-Agent": "CrisisSync/1.0"})
                    response.raise_for_status()
                    parsed = feedparser.parse(response.text)
                    for entry in parsed.entries:
                        _, created = create_raw_item_from_entry(source, entry)
                        if created:
                            created_count += 1
                    source.last_fetched_at = timezone.now()
                    source.save(update_fields=["last_fetched_at"])
                except Exception as exc:
                    failures[source.name] = str(exc)
            job.status = "completed"
            job.details = {"created_items": created_count, "failures": failures}
            self.stdout.write(self.style.SUCCESS(f"Ingestion completed. Created {created_count} raw items."))
        except Exception as exc:
            job.status = "failed"
            job.details = {"error": str(exc)}
            raise
        finally:
            job.finished_at = timezone.now()
            job.save(update_fields=["status", "details", "finished_at"])
