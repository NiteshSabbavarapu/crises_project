from django.contrib import admin

from .models import AlertDecision, AlertDigest, EmailDelivery


@admin.register(AlertDecision)
class AlertDecisionAdmin(admin.ModelAdmin):
    list_display = ("user", "story", "mode", "should_send", "score_snapshot", "created_at")
    list_filter = ("mode", "should_send")
    search_fields = ("user__username", "user__email", "story__headline")


@admin.register(AlertDigest)
class AlertDigestAdmin(admin.ModelAdmin):
    list_display = ("user", "digest_type", "subject", "scheduled_for", "sent_at")
    list_filter = ("digest_type",)
    search_fields = ("user__username", "user__email", "subject")
    filter_horizontal = ("stories",)


@admin.register(EmailDelivery)
class EmailDeliveryAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "subject", "provider_message_id", "sent_at")
    list_filter = ("status",)
    search_fields = ("user__username", "user__email", "subject", "provider_message_id")
