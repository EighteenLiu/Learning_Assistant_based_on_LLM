from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("learning", "0002_slidecontent_layouts_and_translating_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="slidecontent",
            name="source_image_url",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
    ]

