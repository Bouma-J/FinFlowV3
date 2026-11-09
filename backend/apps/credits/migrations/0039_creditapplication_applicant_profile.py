from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("credits", "0038_creditapplication_financing_object"),
    ]

    operations = [
        migrations.AddField(
            model_name="creditapplication",
            name="earning_path",
            field=models.CharField(
                blank=True,
                choices=[
                    ("SALARIE", "Salarié"),
                    ("INDEPENDANT", "Activité"),
                    ("MIXTE", "Les deux"),
                ],
                max_length=20,
                verbose_name="parcours de revenu",
            ),
        ),
        migrations.AddField(
            model_name="creditapplication",
            name="marital_regime",
            field=models.CharField(
                blank=True,
                choices=[
                    ("COMMUNITY", "Communauté"),
                    ("SEPARATION", "Séparation de biens"),
                    ("OTHER", "Autre"),
                ],
                max_length=20,
                verbose_name="régime matrimonial",
            ),
        ),
        migrations.AddField(
            model_name="creditapplication",
            name="spouse_has_income",
            field=models.BooleanField(
                blank=True, null=True, verbose_name="le conjoint a un revenu"
            ),
        ),
        migrations.AddField(
            model_name="creditapplication",
            name="children_count",
            field=models.PositiveIntegerField(
                blank=True, null=True, verbose_name="enfants à charge"
            ),
        ),
        migrations.AddField(
            model_name="creditapplication",
            name="housing_status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("OWNER", "Propriétaire"),
                    ("TENANT", "Locataire"),
                    ("HOSTED", "Hébergé"),
                ],
                max_length=15,
                verbose_name="statut du logement",
            ),
        ),
        migrations.AddField(
            model_name="creditapplication",
            name="housing_seniority_months",
            field=models.PositiveIntegerField(
                blank=True, null=True, verbose_name="ancienneté dans le logement (mois)"
            ),
        ),
        migrations.AddField(
            model_name="creditapplication",
            name="employer_address",
            field=models.CharField(
                blank=True, max_length=255, verbose_name="adresse de l'employeur"
            ),
        ),
        migrations.AddField(
            model_name="creditapplication",
            name="employer_phone",
            field=models.CharField(
                blank=True, max_length=50, verbose_name="téléphone de l'employeur"
            ),
        ),
        migrations.AddField(
            model_name="creditapplication",
            name="employer_sector",
            field=models.CharField(
                blank=True, max_length=150, verbose_name="secteur de l'employeur"
            ),
        ),
        migrations.AddField(
            model_name="creditapplication",
            name="job_seniority_months",
            field=models.PositiveIntegerField(
                blank=True, null=True, verbose_name="ancienneté dans l'emploi (mois)"
            ),
        ),
        migrations.AddField(
            model_name="creditapplication",
            name="career_seniority_months",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                verbose_name="ancienneté professionnelle totale (mois)",
            ),
        ),
        migrations.AddField(
            model_name="creditapplication",
            name="activity_name",
            field=models.CharField(
                blank=True, max_length=200, verbose_name="nom de l'activité"
            ),
        ),
        migrations.AddField(
            model_name="creditapplication",
            name="activity_trade",
            field=models.CharField(
                blank=True, max_length=150, verbose_name="métier de l'activité"
            ),
        ),
        migrations.AddField(
            model_name="creditapplication",
            name="activity_sector",
            field=models.CharField(
                blank=True, max_length=150, verbose_name="secteur de l'activité"
            ),
        ),
        migrations.AddField(
            model_name="creditapplication",
            name="activity_premises_status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("OWNER", "Propriétaire"),
                    ("TENANT", "Locataire"),
                    ("HOSTED", "Hébergé"),
                ],
                max_length=15,
                verbose_name="statut du local d'activité",
            ),
        ),
        migrations.AddField(
            model_name="creditapplication",
            name="activity_ifu",
            field=models.CharField(
                blank=True, max_length=50, verbose_name="IFU de l'activité"
            ),
        ),
        migrations.AlterField(
            model_name="creditapplication",
            name="contract_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("CDI", "CDI"),
                    ("CDD", "CDD"),
                    ("CIVIL_SERVANT", "Fonctionnaire"),
                    ("DAILY", "Journalier"),
                    ("INDEPENDENT", "Indépendant"),
                    ("RETIRED", "Retraité"),
                    ("OTHER", "Autre"),
                ],
                max_length=20,
                verbose_name="type de contrat",
            ),
        ),
    ]
