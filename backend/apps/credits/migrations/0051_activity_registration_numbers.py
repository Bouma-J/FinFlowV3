from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("credits", "0050_activity_profile_identity"),
    ]

    operations = [
        migrations.AddField(
            model_name="creditapplication",
            name="activity_rccm",
            field=models.CharField(blank=True, max_length=50, verbose_name="RCCM de l'activité"),
        ),
        migrations.AddField(
            model_name="creditapplication",
            name="activity_ninea",
            field=models.CharField(blank=True, max_length=50, verbose_name="NINEA de l'activité"),
        ),
    ]
