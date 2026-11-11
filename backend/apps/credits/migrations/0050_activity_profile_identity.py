from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("credits", "0049_es_review_defaults"),
    ]

    operations = [
        migrations.AddField(
            model_name="creditapplication",
            name="activity_nature",
            field=models.CharField(
                blank=True,
                choices=[
                    ("TRADE", "Commerce"),
                    ("CRAFT", "Transformation ou artisanat"),
                    ("SERVICE", "Service"),
                    ("AGRICULTURE", "Agriculture ou élevage"),
                    ("OTHER", "Autre"),
                ],
                max_length=20,
                verbose_name="nature de l'activité",
            ),
        ),
        migrations.AddField(
            model_name="creditapplication",
            name="activity_offer",
            field=models.CharField(blank=True, max_length=255, verbose_name="offre principale"),
        ),
        migrations.AddField(
            model_name="creditapplication",
            name="activity_operation",
            field=models.CharField(
                blank=True,
                choices=[
                    ("SOLO", "Seul"),
                    ("FAMILY", "Avec une aide familiale"),
                    ("EMPLOYEES", "Avec des salariés"),
                ],
                max_length=20,
                verbose_name="mode d'exploitation",
            ),
        ),
        migrations.AddField(
            model_name="creditapplication",
            name="activity_supply",
            field=models.CharField(blank=True, max_length=255, verbose_name="approvisionnement"),
        ),
        migrations.AddField(
            model_name="creditapplication",
            name="activity_authorization",
            field=models.CharField(
                blank=True,
                choices=[
                    ("NONE", "Aucune"),
                    ("PATENT", "Patente"),
                    ("STALL_RIGHT", "Droit de place"),
                    ("OTHER", "Autre"),
                ],
                max_length=20,
                verbose_name="autorisation d'exercer",
            ),
        ),
        migrations.AddField(
            model_name="creditapplication",
            name="activity_authorization_ref",
            field=models.CharField(blank=True, max_length=80, verbose_name="référence de l'autorisation"),
        ),
    ]
