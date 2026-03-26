from django.db import transaction

from intel.models import IntelligenceRun
from news.models import Story

from .models import RumorClaim, RumorEvidence, RumorVerdict


@transaction.atomic
def verify_claim(claim):
    text = claim.text.lower()
    matching_story = Story.objects.filter(headline__icontains=text[:30]).order_by("-priority_score").first()
    if not matching_story:
        for word in [token for token in text.split() if len(token) > 4][:5]:
            matching_story = Story.objects.filter(headline__icontains=word).order_by("-priority_score").first()
            if matching_story:
                break

    if matching_story and matching_story.status == Story.Status.VERIFIED:
        verdict_value = RumorVerdict.Verdict.VERIFIED
        explanation = "This claim aligns with an already verified story in the trusted source database."
        confidence = 80
        official_link = matching_story.official_resource_url
    elif matching_story and matching_story.status == Story.Status.DEBUNKED:
        verdict_value = RumorVerdict.Verdict.FALSE_DEBUNKED
        explanation = "This claim conflicts with a story already marked as debunked by trusted evidence."
        confidence = 85
        official_link = matching_story.official_resource_url
    else:
        verdict_value = RumorVerdict.Verdict.UNCONFIRMED
        explanation = "CrisisSync could not verify this claim from trusted sources yet. Do not forward it."
        confidence = 35
        official_link = ""

    verdict, _ = RumorVerdict.objects.update_or_create(
        claim=claim,
        defaults={
            "verdict": verdict_value,
            "confidence": confidence,
            "explanation": explanation,
            "official_link": official_link,
        },
    )

    RumorEvidence.objects.filter(verdict=verdict).delete()
    if matching_story:
        RumorEvidence.objects.create(
            verdict=verdict,
            story=matching_story,
            url=matching_story.official_resource_url,
            source_name="CrisisSync",
            note=matching_story.headline,
        )

    claim.status = RumorClaim.Status.COMPLETED
    claim.save(update_fields=["status", "updated_at"])

    IntelligenceRun.objects.create(
        task_type=IntelligenceRun.TaskType.RUMOR,
        request_payload={"claim_id": claim.id, "text": claim.text},
        response_payload={"verdict": verdict.verdict, "confidence": verdict.confidence},
        success=True,
    )
    return verdict
