from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("credits", "0052_activity_registration_scans"),
    ]

    operations = [
        migrations.AddField(
            model_name="financialanalysis",
            name="is_draft",
            field=models.BooleanField(
                default=False,
                help_text="Analyse enregistrée pour être reprise. Elle ne sert ni à la soumission ni au comité.",
                verbose_name="brouillon",
            ),
        ),
    ]
