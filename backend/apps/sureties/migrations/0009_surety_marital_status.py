from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sureties", "0008_alter_surety_manager_id_document_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="surety",
            name="marital_status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("SINGLE", "Célibataire"),
                    ("MARRIED", "Marié(e)"),
                    ("DIVORCED", "Divorcé(e)"),
                    ("WIDOWED", "Veuf/Veuve"),
                ],
                max_length=15,
                verbose_name="situation matrimoniale",
            ),
        ),
        migrations.AddField(
            model_name="surety",
            name="matrimonial_regime",
            field=models.CharField(
                blank=True,
                choices=[
                    ("COMMUNITY", "Communauté de biens"),
                    ("SEPARATION", "Séparation de biens"),
                ],
                max_length=15,
                verbose_name="régime matrimonial",
            ),
        ),
    ]
