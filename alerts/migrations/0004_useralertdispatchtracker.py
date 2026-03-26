from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("alerts", "0003_useralertsnapshot"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserAlertDispatchTracker",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("channel", models.CharField(default="email", max_length=20)),
                ("last_checked_at", models.DateTimeField(blank=True, null=True)),
                ("last_sent_at", models.DateTimeField(blank=True, null=True)),
                ("last_story_fetched_at", models.DateTimeField(blank=True, null=True)),
                ("last_delivery_status", models.CharField(blank=True, max_length=20)),
                ("last_response_body", models.JSONField(blank=True, default=dict)),
                ("last_error_message", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "last_delivery",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="dispatch_trackers",
                        to="alerts.emaildelivery",
                    ),
                ),
                (
                    "last_digest",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="dispatch_trackers",
                        to="alerts.alertdigest",
                    ),
                ),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="alert_dispatch_tracker",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-updated_at"],
            },
        ),
    ]
