from django.contrib import admin

from .models import IntelligenceRun


@admin.register(IntelligenceRun)
class IntelligenceRunAdmin(admin.ModelAdmin):
    list_display = ("task_type", "story", "success", "created_at")
    list_filter = ("task_type", "success")
