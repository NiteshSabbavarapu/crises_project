from django.contrib import admin

from .models import JobRun


@admin.register(JobRun)
class JobRunAdmin(admin.ModelAdmin):
    list_display = ("command_name", "status", "created_at", "finished_at")
    list_filter = ("command_name", "status")
