from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from jobs.models import JobRun
from rumors.models import RumorClaim
from rumors.services import verify_claim


class Command(BaseCommand):
    help = "Verify a rumor claim against the stored story corpus."

    def add_arguments(self, parser):
        parser.add_argument("claim_id", type=int)

    def handle(self, *args, **options):
        job = JobRun.objects.create(command_name="verify_rumor", status="started")
        try:
            claim = RumorClaim.objects.get(pk=options["claim_id"])
            verdict = verify_claim(claim)
            job.status = "completed"
            job.details = {"claim_id": claim.id, "verdict": verdict.verdict}
            self.stdout.write(self.style.SUCCESS(f"Rumor claim {claim.id} marked as {verdict.verdict}."))
        except RumorClaim.DoesNotExist as exc:
            job.status = "failed"
            job.details = {"error": f"Claim {options['claim_id']} not found."}
            raise CommandError(f"Claim {options['claim_id']} not found.") from exc
        finally:
            job.finished_at = timezone.now()
            job.save(update_fields=["status", "details", "finished_at"])
