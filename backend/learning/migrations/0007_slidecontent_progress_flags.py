from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("learning", "0006_summaryrecord_mind_map"),
    ]

    operations = [
        migrations.AddField(
            model_name="slidecontent",
            name="preview_done",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="slidecontent",
            name="translation_done",
            field=models.BooleanField(default=False),
        ),
    ]
