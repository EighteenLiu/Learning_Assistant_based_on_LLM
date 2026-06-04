from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("learning", "0011_courseware_translation_chunk_progress"),
    ]

    operations = [
        migrations.AddField(
            model_name="summaryrecord",
            name="learning_suggestions",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
