from django.db import models


class JobRun(models.Model):
    command_name = models.CharField(max_length=120)
    status = models.CharField(max_length=20, default="started")
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
