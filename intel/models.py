from django.db import models

from news.models import Story


class IntelligenceRun(models.Model):
    """Audit record for AI and heuristic intelligence jobs."""

    class TaskType(models.TextChoices):
        SUMMARY = "summary", "Summary"
        ACTIONS = "actions", "Actions"
        SCORING = "scoring", "Scoring"
        RUMOR = "rumor", "Rumor"

    story = models.ForeignKey(Story, on_delete=models.CASCADE, null=True, blank=True)
    task_type = models.CharField(max_length=20, choices=TaskType.choices)
    provider = models.CharField(max_length=32, blank=True, help_text="AI or rules engine used for this run.")
    model_name = models.CharField(max_length=64, blank=True, help_text="Exact model identifier used for this run.")
    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    success = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.task_type} via {self.provider or 'rules'}"
