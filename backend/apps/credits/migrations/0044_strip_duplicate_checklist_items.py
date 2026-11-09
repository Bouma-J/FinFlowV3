from django.db import migrations

# Pièces déjà demandées sur la fiche client, dans le prêt ou dans l'analyse.
_COLLECTED_ELSEWHERE = {
    "pièce d'identité",
    "lettre de demande",
    "relevés bancaires (6 mois)",
    "justificatifs de revenus / bulletins de salaire",
    "rccm",
    "ifu / ninea",
    "états financiers (2 derniers exercices)",
}


def strip_duplicate_pieces(apps, schema_editor):
    CreditApplication = apps.get_model("credits", "CreditApplication")
    for application in CreditApplication.objects.all().iterator():
        raw = application.document_checklist or []
        if not isinstance(raw, list):
            continue
        kept = []
        changed = False
        for item in raw:
            label = item.get("label") if isinstance(item, dict) else item
            if str(label or "").strip().lower() in _COLLECTED_ELSEWHERE:
                changed = True
                continue
            kept.append(item)
        if changed:
            application.document_checklist = kept
            application.save(update_fields=["document_checklist"])


class Migration(migrations.Migration):

    dependencies = [
        ("credits", "0043_creditapplication_pep_details"),
    ]

    operations = [
        migrations.RunPython(strip_duplicate_pieces, migrations.RunPython.noop),
    ]
