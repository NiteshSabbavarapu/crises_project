from django.contrib import admin

from .models import RumorClaim, RumorEvidence, RumorVerdict


class RumorEvidenceInline(admin.TabularInline):
    model = RumorEvidence
    extra = 0


@admin.register(RumorClaim)
class RumorClaimAdmin(admin.ModelAdmin):
    list_display = ("id", "submitter", "city", "area", "status", "created_at")
    list_filter = ("status", "city")
    search_fields = ("text", "submitter__username", "submitter__email")


@admin.register(RumorVerdict)
class RumorVerdictAdmin(admin.ModelAdmin):
    list_display = ("claim", "verdict", "confidence", "verified_at")
    list_filter = ("verdict",)
    inlines = [RumorEvidenceInline]
