from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("learning", "0009_courseware_last_error"),
    ]

    operations = [
        migrations.AddField(
            model_name="courseware",
            name="translation_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="courseware",
            name="translation_duration_seconds",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
