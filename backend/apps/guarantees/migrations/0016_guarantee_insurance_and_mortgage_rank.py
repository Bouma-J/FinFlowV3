from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("guarantees", "0015_guarantee_title_uniqueness"),
    ]

    operations = [
        migrations.AddField(
            model_name="guarantee",
            name="insured_amount",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=18,
                null=True,
                verbose_name="montant assuré",
            ),
        ),
        migrations.AddField(
            model_name="guarantee",
            name="insurance_end_date",
            field=models.DateField(blank=True, null=True, verbose_name="fin de l'assurance"),
        ),
        migrations.AddField(
            model_name="guarantee",
            name="mortgage_rank",
            field=models.CharField(
                blank=True,
                choices=[("1", "1er rang"), ("2", "2e rang"), ("OTHER", "Autre")],
                max_length=10,
                verbose_name="rang de l'hypothèque",
            ),
        ),
        migrations.AddField(
            model_name="guarantee",
            name="prior_lien_amount",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=18,
                null=True,
                verbose_name="montant des inscriptions antérieures",
            ),
        ),
    ]
