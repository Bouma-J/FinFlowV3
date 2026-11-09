from django.db import migrations, models

import apps.credits.models


class Migration(migrations.Migration):

    dependencies = [
        ("credits", "0045_field_visit_observations"),
    ]

    operations = [
        migrations.AddField(
            model_name="fieldvisit",
            name="minutes",
            field=models.FileField(
                blank=True,
                max_length=255,
                upload_to=apps.credits.models.visit_file_path,
                verbose_name="PV de visite",
            ),
        ),
    ]
