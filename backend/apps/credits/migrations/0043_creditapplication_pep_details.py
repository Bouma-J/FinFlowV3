from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("credits", "0042_external_bank_account"),
    ]

    operations = [
        migrations.AddField(
            model_name="creditapplication",
            name="pep_details",
            field=models.TextField(blank=True, verbose_name="explication PPE"),
        ),
    ]
