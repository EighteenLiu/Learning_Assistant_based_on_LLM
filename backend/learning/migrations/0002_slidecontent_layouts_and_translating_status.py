from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("learning", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="slidecontent",
            name="source_layout",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="slidecontent",
            name="translated_layout",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name="courseware",
            name="status",
            field=models.CharField(
                choices=[
                    ("uploaded", "Uploaded"),
                    ("translating", "Translating"),
                    ("translated", "Translated"),
                    ("failed", "Failed"),
                ],
                default="uploaded",
                max_length=20,
            ),
        ),
    ]

