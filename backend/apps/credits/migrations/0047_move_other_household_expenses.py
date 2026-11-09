from django.db import migrations


def move_other_household_expenses(apps, schema_editor):
    FinancialAnalysis = apps.get_model("credits", "FinancialAnalysis")
    for analysis in FinancialAnalysis.objects.all().iterator():
        amount = analysis.other_household_expenses
        if not amount:
            continue
        details = analysis.analysis_details if isinstance(analysis.analysis_details, dict) else {}
        rows = details.get("extra_charges")
        if not isinstance(rows, list):
            rows = []
        rows.append({"label": "Autres charges", "amount": format(amount, "f")})
        details["extra_charges"] = rows
        analysis.analysis_details = details
        analysis.other_household_expenses = 0
        analysis.save(update_fields=["analysis_details", "other_household_expenses"])


class Migration(migrations.Migration):

    dependencies = [
        ("credits", "0046_fieldvisit_minutes"),
    ]

    operations = [
        migrations.RunPython(move_other_household_expenses, migrations.RunPython.noop),
    ]
