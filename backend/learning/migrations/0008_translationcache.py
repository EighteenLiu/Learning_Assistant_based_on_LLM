from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("learning", "0007_slidecontent_progress_flags"),
    ]

    operations = [
        migrations.CreateModel(
            name="TranslationCache",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("cache_key", models.CharField(db_index=True, max_length=64, unique=True)),
                ("translation_type", models.CharField(db_index=True, default="slide_text", max_length=32)),
                ("source_language", models.CharField(default="en", max_length=10)),
                ("target_language", models.CharField(default="zh", max_length=10)),
                ("model_name", models.CharField(blank=True, default="", max_length=120)),
                ("term_hint_hash", models.CharField(blank=True, default="", max_length=64)),
                ("source_hash", models.CharField(db_index=True, max_length=64)),
                ("source_text", models.TextField()),
                ("translated_text", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ("-updated_at", "-id"),
            },
        ),
        migrations.AddIndex(
            model_name="translationcache",
            index=models.Index(
                fields=["translation_type", "model_name", "term_hint_hash", "source_hash"],
                name="lrn_tc_type_model_term_src_idx",
            ),
        ),
    ]
