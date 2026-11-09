from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("credits", "0039_creditapplication_applicant_profile"),
    ]

    operations = [
        migrations.AddField(
            model_name="creditapplication",
            name="employment_profession",
            field=models.CharField(blank=True, max_length=150, verbose_name="profession"),
        ),
        migrations.AddField(
            model_name="creditapplication",
            name="job_title",
            field=models.CharField(blank=True, max_length=150, verbose_name="poste occupé"),
        ),
    ]
