from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="useralertpreference",
            name="frequency",
            field=models.CharField(
                choices=[("30min", "Every 30 Minutes"), ("hourly", "Hourly"), ("critical_only", "Critical Only")],
                default="30min",
                max_length=20,
            ),
        ),
    ]
