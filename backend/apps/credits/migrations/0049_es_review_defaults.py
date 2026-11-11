from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("credits", "0048_activity_premises_choices"),
    ]

    operations = [
        migrations.AlterField(
            model_name="financialanalysis",
            name="exclusion_list_ok",
            field=models.BooleanField(default=False, verbose_name="activité hors liste d'exclusion"),
        ),
        migrations.AlterField(
            model_name="financialanalysis",
            name="es_regulatory_compliance",
            field=models.BooleanField(default=False, verbose_name="conformité réglementaire E&S"),
        ),
    ]
