from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("credits", "0040_creditapplication_employment_profession"),
    ]

    operations = [
        migrations.AddField(
            model_name="creditapplication",
            name="contract_end_date",
            field=models.DateField(blank=True, null=True, verbose_name="date de fin du contrat"),
        ),
    ]
