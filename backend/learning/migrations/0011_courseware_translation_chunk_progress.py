from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("learning", "0010_courseware_translation_duration"),
    ]

    operations = [
        migrations.AddField(
            model_name="courseware",
            name="translation_total_chunks",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="courseware",
            name="translation_completed_chunks",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="courseware",
            name="translation_current_slide_no",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
