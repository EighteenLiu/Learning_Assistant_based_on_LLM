from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("learning", "0008_translationcache"),
    ]

    operations = [
        migrations.AddField(
            model_name="courseware",
            name="last_error",
            field=models.TextField(blank=True, default=""),
        ),
    ]
