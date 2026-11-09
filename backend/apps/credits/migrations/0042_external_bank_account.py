import apps.credits.models
import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("credits", "0041_creditapplication_contract_end_date"),
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExternalBankAccount",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="créé le")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="modifié le")),
                ("institution_name", models.CharField(blank=True, max_length=200, verbose_name="nom de l'institution")),
                ("opened_on", models.DateField(blank=True, null=True, verbose_name="date d'ouverture")),
                ("account_number", models.CharField(blank=True, max_length=50, verbose_name="numéro de compte")),
                ("credit_movement_count", models.PositiveIntegerField(blank=True, null=True, verbose_name="mouvements créditeurs sur 3 mois")),
                ("credit_movement_volume", models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True, verbose_name="volume des mouvements créditeurs")),
                ("statement", models.FileField(blank=True, max_length=255, upload_to=apps.credits.models.credit_file_path, verbose_name="relevé de compte")),
                ("application", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="external_accounts", to="credits.creditapplication", verbose_name="dossier")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="%(app_label)s_%(class)s_set", to="tenants.tenant", verbose_name="filiale")),
            ],
            options={
                "verbose_name": "compte hors institution",
                "verbose_name_plural": "comptes hors institution",
                "ordering": ["created_at"],
            },
        ),
    ]
