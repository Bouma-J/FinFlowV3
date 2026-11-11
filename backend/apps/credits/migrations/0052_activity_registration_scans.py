from django.db import migrations, models

import apps.credits.models


class Migration(migrations.Migration):

    dependencies = [
        ("credits", "0051_activity_registration_numbers"),
    ]

    operations = [
        migrations.AddField(
            model_name="creditapplication",
            name="activity_ifu_scan",
            field=models.FileField(
                blank=True,
                max_length=255,
                upload_to=apps.credits.models.credit_file_path,
                verbose_name="fichier IFU",
            ),
        ),
        migrations.AddField(
            model_name="creditapplication",
            name="activity_rccm_scan",
            field=models.FileField(
                blank=True,
                max_length=255,
                upload_to=apps.credits.models.credit_file_path,
                verbose_name="fichier RCCM",
            ),
        ),
        migrations.AddField(
            model_name="creditapplication",
            name="activity_ninea_scan",
            field=models.FileField(
                blank=True,
                max_length=255,
                upload_to=apps.credits.models.credit_file_path,
                verbose_name="fichier NINEA",
            ),
        ),
    ]
