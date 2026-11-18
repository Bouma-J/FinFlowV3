from django.db import migrations, models


def pend_unformalized(apps, schema_editor):
    Guarantee = apps.get_model("guarantees", "Guarantee")
    Guarantee.objects.filter(
        status="ACTIVE",
        formalized_at__isnull=True,
    ).update(status="PENDING")


def restore_active(apps, schema_editor):
    Guarantee = apps.get_model("guarantees", "Guarantee")
    Guarantee.objects.filter(status="PENDING").update(status="ACTIVE")


class Migration(migrations.Migration):

    dependencies = [
        ("guarantees", "0016_guarantee_insurance_and_mortgage_rank"),
    ]

    operations = [
        migrations.AlterField(
            model_name="guarantee",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING", "En attente de formalisation"),
                    ("ACTIVE", "Active"),
                    ("RELEASED", "Mainlevée"),
                    ("REALIZED", "Réalisée"),
                    ("TRANSFERRED", "Transférée"),
                ],
                db_index=True,
                default="PENDING",
                max_length=20,
            ),
        ),
        migrations.RunPython(pend_unformalized, restore_active),
    ]
