from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sureties", "0009_surety_marital_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="surety",
            name="monthly_charges",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=18,
                null=True,
                verbose_name="charges mensuelles",
            ),
        ),
        migrations.AddField(
            model_name="surety",
            name="existing_monthly_payments",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=18,
                null=True,
                verbose_name="mensualités déjà supportées",
            ),
        ),
    ]
