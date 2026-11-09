import uuid

import django.db.models.deletion
from django.db import migrations, models

import apps.credits.models


class Migration(migrations.Migration):

    dependencies = [
        ("credits", "0044_strip_duplicate_checklist_items"),
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="fieldvisit",
            name="visited_places",
            field=models.JSONField(blank=True, default=list, verbose_name="lieux visités"),
        ),
        migrations.AddField(
            model_name="fieldvisit",
            name="person_met",
            field=models.CharField(
                blank=True,
                choices=[
                    ("CLIENT", "Le client"),
                    ("OTHER", "Quelqu'un d'autre"),
                    ("ABSENT", "Personne"),
                ],
                max_length=20,
                verbose_name="personne rencontrée",
            ),
        ),
        migrations.AddField(
            model_name="fieldvisit",
            name="conclusion",
            field=models.CharField(
                blank=True,
                choices=[
                    ("COHERENT", "Conforme au dossier"),
                    ("GAP", "Écart constaté"),
                ],
                max_length=20,
                verbose_name="conclusion",
            ),
        ),
        migrations.CreateModel(
            name="FieldVisitPhoto",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="créé le")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="modifié le")),
                ("image", models.ImageField(max_length=255, upload_to=apps.credits.models.visit_photo_path, verbose_name="photo")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="%(app_label)s_%(class)s_set", to="tenants.tenant", verbose_name="filiale")),
                ("visit", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="photos", to="credits.fieldvisit", verbose_name="visite")),
            ],
            options={
                "verbose_name": "photo de visite",
                "verbose_name_plural": "photos de visite",
                "ordering": ["created_at"],
            },
        ),
    ]
