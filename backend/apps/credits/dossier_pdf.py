"""Export PDF d'un dossier de crédit, à la charte de la filiale.

Les pièces jointes sont inventoriées (nom, type, date). Leurs fichiers
ne sont pas fusionnés dans le document.
"""
from __future__ import annotations

import io
import os
from decimal import Decimal
from xml.sax.saxutils import escape

from django.utils import timezone

from apps.notifications.email_brand import colors_for_tenant, readable_text

_FONT = "DossierSans"
_FONT_B = "DossierSans-Bold"
_REGISTERED = False


def _register_fonts() -> tuple[str, str]:
    global _REGISTERED
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if _REGISTERED:
        return _FONT, _FONT_B
    pairs = (
        (
            r"C:\Windows\Fonts\arial.ttf",
            r"C:\Windows\Fonts\arialbd.ttf",
        ),
        (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ),
        (
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ),
    )
    for regular, bold in pairs:
        if os.path.isfile(regular) and os.path.isfile(bold):
            pdfmetrics.registerFont(TTFont(_FONT, regular))
            pdfmetrics.registerFont(TTFont(_FONT_B, bold))
            _REGISTERED = True
            return _FONT, _FONT_B
    _REGISTERED = True
    return "Helvetica", "Helvetica-Bold"


def _color(hex_value: str):
    from reportlab.lib.colors import Color

    raw = hex_value.lstrip("#")
    return Color(
        int(raw[0:2], 16) / 255,
        int(raw[2:4], 16) / 255,
        int(raw[4:6], 16) / 255,
    )


def _money(amount, currency: str) -> str:
    if amount in (None, ""):
        return "—"
    try:
        number = Decimal(str(amount))
    except Exception:
        return str(amount)
    if number == number.to_integral_value():
        text = f"{number:,.0f}"
    else:
        text = f"{number:,.2f}"
    return f"{text.replace(',', ' ')} {currency or ''}".strip()


def _date(value) -> str:
    if not value:
        return "—"
    if hasattr(value, "tzinfo") and getattr(value, "tzinfo", None) is not None:
        value = timezone.localtime(value)
    if hasattr(value, "strftime"):
        if hasattr(value, "hour"):
            return value.strftime("%d/%m/%Y %H:%M")
        return value.strftime("%d/%m/%Y")
    return str(value)


def _yes(value) -> str:
    if value is None or value == "":
        return "—"
    return "Oui" if value else "Non"


def _text(value) -> str:
    text = "" if value is None else str(value).strip()
    return text or "—"


def _filled(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def build_dossier_pdf(application, user) -> bytes:
    """Produit le PDF du dossier. ``user`` sert au filtre d'exposition."""
    font, font_b = _register_fonts()
    brand = colors_for_tenant(application.tenant)
    payload = _collect(application, user)
    return _render(payload, brand, font, font_b)


def _collect(application, user) -> dict:
    from apps.audit.models import AuditLog
    from apps.contracts.models import GeneratedContract
    from apps.credits.amounts import reference_amount
    from apps.credits.models import Loan
    from apps.sureties.models import SuretyEngagement
    from apps.workflow.models import ApprovalCondition, ApprovalTask, WorkflowInstance

    client = application.client
    currency = application.currency or "XOF"
    amount = reference_amount(application)
    product = getattr(application, "product", None)
    agency = getattr(application, "agency", None)
    financing = getattr(application, "financing_object", None)

    identity = [
        ("Référence", application.reference or "—"),
        ("Statut", application.get_status_display()),
        ("Client", client.display_name if client else "—"),
        ("Type de client", client.get_client_type_display() if client else "—"),
        ("Matricule", (client.cbs_client_id or client.reference) if client else "—"),
        ("Produit", getattr(product, "label", "") or "—"),
        ("Agence", f"{agency.code} — {agency.name}" if agency else "—"),
        ("Montant de référence", _money(amount, currency)),
        ("Montant demandé", _money(application.amount_requested, currency)),
        ("Montant proposé", _money(application.amount_proposed, currency)),
        ("Montant approuvé", _money(application.amount_approved, currency)),
        ("Durée", f"{application.duration_months} mois"),
        ("Périodicité", application.get_periodicity_display()),
        ("Mécanisme", application.get_repayment_mechanism_display()),
        ("Taux d'intérêt", _rate(application.interest_rate)),
        ("Frais de dossier", _rate(application.fees_rate)),
        ("Épargne obligatoire", _rate(application.mandatory_savings_rate)),
        ("Première échéance", _date(application.first_due_date)),
        ("Dernière échéance", _date(application.last_due_date)),
        ("Objet", application.get_purpose_type_display() if application.purpose_type else "—"),
        ("Objet de financement", getattr(financing, "label", "") or "—"),
        ("Niveau de risque", str(application.risk_level) if application.risk_level else "—"),
        ("Décision", _date(application.decision_date)),
        ("Soumis le", _date(application.submitted_at)),
        ("Soumis par", _person(application.submitted_by)),
        ("Mis en place le", _date(application.disbursed_at)),
        ("Créé le", _date(application.created_at)),
        ("Créé par", _person(application.created_by)),
    ]
    if application.purpose:
        identity.append(("Détail de la demande", application.purpose))

    fees = [
        (
            fee.label,
            f"{fee.value} %" if fee.mode == fee.Mode.PERCENT else _money(fee.value, currency),
        )
        for fee in application.extra_fees.all()
    ]

    client_rows = _client_rows(client)
    profile_blocks = _profile_blocks(application)
    analyses = _analyses(application, currency)
    guarantees = _guarantees(application, currency)
    sureties = _sureties(application, currency)
    visits = [
        (
            _date(visit.visit_date),
            _person(visit.visited_by),
            visit.visitor_role or "—",
            visit.geo_coordinates or "—",
            visit.report or "—",
        )
        for visit in application.field_visits.select_related("visited_by").all()
    ]
    documents = _documents(application)
    contracts = [
        (
            item.template_name,
            item.get_status_display(),
            _date(item.created_at),
            _person(item.created_by),
            _date(item.signed_at) if item.signed_at else "—",
        )
        for item in application.generated_contracts.exclude(
            status=GeneratedContract.Status.CANCELLED
        ).select_related("created_by")
    ]
    schedule = _schedule(application, currency)
    exposure = _exposure(application, user, currency)

    try:
        loan = application.loan
    except Loan.DoesNotExist:
        loan = None
    loan_rows = []
    if loan is not None:
        loan_rows = [
            ("Statut du prêt", loan.get_status_display()),
            ("Capital", _money(loan.principal, currency)),
            ("Taux", _rate(loan.interest_rate)),
            ("Mise en place", _date(loan.disbursed_at)),
            ("Première échéance", _date(loan.first_due_date)),
            ("Référence CBS", loan.core_banking_reference or loan.cbs_contract_number or "—"),
        ]

    cbs_rows = [
        ("N° demande CBS", application.cbs_demande_number or "—"),
        ("Réf. demande CBS", application.cbs_demande_ref or "—"),
        ("N° contrat CBS", application.cbs_contract_number or "—"),
        ("Date d'opération CBS", _date(application.cbs_operation_date)),
    ]

    conditions = [
        (
            item.get_status_display(),
            item.description or "—",
            _person(item.issued_by),
        )
        for item in ApprovalCondition.all_tenants.filter(
            application=application
        ).select_related("issued_by")
    ]

    from django.contrib.contenttypes.models import ContentType

    ct = ContentType.objects.get_for_model(application.__class__)
    instance_ids = list(
        WorkflowInstance.all_tenants.filter(
            content_type=ct, object_id=application.pk
        ).values_list("id", flat=True)
    )
    tasks = ApprovalTask.all_tenants.filter(instance_id__in=instance_ids).select_related(
        "step", "acted_by"
    ).order_by("step__order", "created_at")
    decisions = [
        (
            task.step.name if task.step_id else "—",
            task.get_status_display(),
            task.get_opinion_display() if task.opinion else "—",
            _person(task.acted_by) if task.acted_by_id else "—",
            _date(task.acted_at),
            task.decision_comment or "—",
        )
        for task in tasks
    ]
    history = []
    creator = application.created_by
    history.append((_date(application.created_at), "Création", _person(creator), ""))
    logs = AuditLog.objects.filter(
        action=AuditLog.Action.WORKFLOW,
        model_label=application._meta.label,
        object_id=str(application.pk),
    ).select_related("user").order_by("timestamp")
    for log in logs:
        history.append((
            _date(log.timestamp),
            (log.changes or {}).get("event", "Circuit"),
            _person(log.user) if log.user_id else "—",
            (log.changes or {}).get("detail", "") or "",
        ))

    return {
        "filiale": getattr(application.tenant, "name", "") or "FIN_FLOW",
        "filiale_meta": " · ".join(
            part for part in (
                getattr(application.tenant, "address", ""),
                getattr(application.tenant, "phone", ""),
                getattr(application.tenant, "email", ""),
            ) if part
        ),
        "logo": _logo_bytes(application.tenant),
        "reference": application.reference or str(application.pk)[:8],
        "client_name": client.display_name if client else "—",
        "headline_amount": _money(amount, currency),
        "status": application.get_status_display(),
        "generated_at": timezone.localtime(timezone.now()).strftime("%d/%m/%Y à %H:%M"),
        "identity": identity,
        "fees": fees,
        "client_rows": client_rows,
        "profile_blocks": profile_blocks,
        "analyses": analyses,
        "guarantees": guarantees,
        "sureties": sureties,
        "visits": visits,
        "documents": documents,
        "contracts": contracts,
        "schedule": schedule,
        "exposure": exposure,
        "loan_rows": loan_rows,
        "cbs_rows": cbs_rows,
        "conditions": conditions,
        "decisions": decisions,
        "history": history,
    }


def _rate(value) -> str:
    if value in (None, ""):
        return "—"
    return f"{value} %"


def _optional_decimal(value):
    if value in (None, ""):
        return None
    try:
        number = Decimal(str(value))
    except Exception:
        return None
    return number if number.is_finite() else None


def _variation_text(current, previous) -> str:
    if current is None or previous is None or previous == 0:
        return "—"
    percent = ((current - previous) / abs(previous) * Decimal("100")).quantize(Decimal("0.1"))
    sign = "+" if percent > 0 else ""
    return f"{sign}{percent} %"


def _spread_text(current, previous, currency: str) -> str:
    if current is None or previous is None:
        return "—"
    return _money(current - previous, currency)


def _comparison_tables(item, currency: str) -> list[dict]:
    """États comparatifs calculés à l'export, sans traiter une case vide comme zéro."""
    tables = []
    current_turnover = _optional_decimal(item.turnover)
    previous_turnover = _optional_decimal(item.turnover_prev)
    current_result = _optional_decimal(item.net_result)
    previous_result = _optional_decimal(item.net_result_prev)
    statement = []
    if current_turnover is not None or previous_turnover is not None:
        statement.append((
            "Chiffre d'affaires", _money(current_turnover, currency), _money(previous_turnover, currency),
            _spread_text(current_turnover, previous_turnover, currency), _variation_text(current_turnover, previous_turnover),
        ))
    if current_result is not None or previous_result is not None:
        statement.append((
            "Résultat net", _money(current_result, currency), _money(previous_result, currency),
            _spread_text(current_result, previous_result, currency), _variation_text(current_result, previous_result),
        ))
    if statement:
        tables.append({
            "title": "Compte de résultat — période en cours et période précédente",
            "headers": ["Rubrique", "Période en cours", "Période précédente", "Écart", "Variation"],
            "rows": statement,
            "widths": [40, 34, 38, 32, 30],
        })
    details = item.analysis_details or {}
    history = details.get("history") if isinstance(details.get("history"), list) else []
    history_rows, prior_turnover, prior_result = [], None, None
    for row in history:
        if not isinstance(row, dict):
            continue
        turnover = _optional_decimal(row.get("turnover"))
        result = _optional_decimal(row.get("net_result"))
        history_rows.append((
            str(row.get("period") or "—"), _money(turnover, currency), _variation_text(turnover, prior_turnover),
            _money(result, currency), _variation_text(result, prior_result), _money(_optional_decimal(row.get("equity")), currency),
        ))
        prior_turnover, prior_result = turnover, result
    if history_rows:
        tables.append({
            "title": "Historique — variation par rapport à la ligne précédente",
            "headers": ["Période", "Chiffre d'affaires", "Variation", "Résultat", "Variation", "Capitaux propres"],
            "rows": history_rows,
            "widths": [36, 32, 24, 30, 24, 28],
        })
    products = details.get("products") if isinstance(details.get("products"), list) else []
    product_rows = []
    for row in products:
        if not isinstance(row, dict) or not (row.get("name") or row.get("sale_price") or row.get("unit_cost")):
            continue
        quantity = _optional_decimal(row.get("quantity"))
        sale = _optional_decimal(row.get("sale_price"))
        cost = _optional_decimal(row.get("unit_cost"))
        total = None if quantity is None or sale is None else quantity * sale
        margin = None if total is None or cost is None else quantity * (sale - cost)
        product_rows.append((
            str(row.get("name") or "—"), "—" if quantity is None else f"{quantity:,.0f}".replace(",", " "),
            _money(cost, currency), _money(sale, currency), _money(total, currency), _money(margin, currency),
        ))
    if product_rows:
        tables.append({
            "title": "Fiches produits / services — période de référence",
            "headers": ["Articles / produits", "Quantité", "Prix de revient", "Prix de vente", "Valeur totale", "Marge brute prévisionnelle"],
            "rows": product_rows,
            "widths": [36, 20, 28, 28, 30, 32],
        })
    stocks = details.get("stocks") if isinstance(details.get("stocks"), list) else []
    stock_rows = []
    for row in stocks:
        if not isinstance(row, dict) or not (row.get("name") or row.get("quantity") or row.get("unit_cost")):
            continue
        quantity = _optional_decimal(row.get("quantity"))
        cost = _optional_decimal(row.get("unit_cost"))
        impairment = _optional_decimal(row.get("impaired_value"))
        gross = None if quantity is None or cost is None else quantity * cost
        net = None if gross is None or impairment is None else gross - impairment
        stock_rows.append((
            str(row.get("name") or "—"), "—" if quantity is None else f"{quantity:,.0f}".replace(",", " "),
            _money(cost, currency), _money(impairment, currency), _money(net, currency),
        ))
    if stock_rows:
        tables.append({
            "title": "Stock — valeur nette",
            "headers": ["Article", "Quantité", "Coût unitaire", "Dépréciation", "Valeur nette"],
            "rows": stock_rows,
            "widths": [48, 24, 34, 34, 34],
        })
    return tables


def _tpe_rows(item, currency: str) -> list[tuple]:
    from apps.credits.analysis_details import apply_tpe_safety, detail_metrics

    metrics = detail_metrics(item)
    try:
        installment = item.monthly_new_installment
    except Exception:
        installment = None
    saved = {"repayment_capacity": item.repayment_capacity, "installment": installment}
    apply_tpe_safety(saved, item)
    metrics.update(saved)
    labels = {
        "tpe_monthly_sales": "CA mensuel retenu (méthode TPE)",
        "tpe_sales_gap": "Écart CA retenu − CA déclaré ramené au mois",
        "tpe_monthly_purchases": "Achats mensuels retenus",
        "tpe_cash_theoretical": "Trésorerie théorique depuis le dernier achat",
        "tpe_cash_gap": "Écart de trésorerie constaté",
        "tpe_safety_available": "Capacité disponible après retenue de prudence",
    }
    rows = []
    for key, label in labels.items():
        if metrics.get(key) is not None:
            rows.append((label, _money(metrics[key], currency)))
    conclusion = {
        "COHERENT": "Cohérent",
        "TO_JUSTIFY": "À justifier",
        "INCOHERENT": "Incohérent",
    }.get(metrics.get("tpe_cash_conclusion") or "")
    if conclusion:
        rows.append(("Conclusion du contrôle de caisse", conclusion))
    if metrics.get("tpe_safety_coverage") is not None:
        rows.append(("Couverture de la nouvelle échéance après retenue", f"{metrics['tpe_safety_coverage']} ×"))
    return rows


def _person(user) -> str:
    if user is None:
        return "—"
    name = ""
    if hasattr(user, "get_full_name"):
        name = (user.get_full_name() or "").strip()
    return name or getattr(user, "email", None) or str(user)


def _client_rows(client) -> list[tuple[str, str]]:
    if client is None:
        return []
    rows = [
        ("Nom", client.display_name),
        ("Type", client.get_client_type_display()),
        ("Téléphone", client.phone or "—"),
        ("E-mail", client.email or "—"),
        ("Adresse", " ".join(part for part in (client.address, client.city, client.country) if part) or "—"),
        ("Pièce d'identité", client.national_id or "—"),
        ("Profession", getattr(client, "profession", "") or "—"),
        ("Date de naissance", _date(getattr(client, "birth_date", None))),
        ("Compte", client.cbs_account_number or "—"),
        ("Identifiant CBS", client.cbs_client_id or "—"),
    ]
    if getattr(client, "company_name", ""):
        rows.extend([
            ("Raison sociale", client.company_name),
            ("RCCM", getattr(client, "rccm", "") or "—"),
            ("IFU", getattr(client, "ifu", "") or "—"),
        ])
    return rows


def _profile_blocks(application) -> list[tuple[str, list[tuple[str, str]]]]:
    blocks = []

    def add(title, pairs):
        kept = [(label, _text(value)) for label, value in pairs if _filled(value)]
        if kept:
            blocks.append((title, kept))

    add("Activité et commerce", [
        ("Date de démarrage", _date(application.activity_start_date) if application.activity_start_date else ""),
        ("Adresse exacte", application.exact_address),
        ("Clientèle", application.clientele),
        ("Zone de chalandise", application.catchment_area),
        ("Régime fiscal", application.get_tax_regime_display() if application.tax_regime else ""),
        ("Délai moyen clients (jours)", application.avg_client_payment_days),
        ("Délai moyen fournisseurs (jours)", application.avg_supplier_payment_days),
        ("Statut des locaux", application.get_premises_status_display() if application.premises_status else ""),
        ("Coût total du projet", application.project_total_cost),
        ("Apport personnel", application.personal_contribution),
        ("Quotité financée", application.financed_quota),
    ])
    add("Demandeur et emploi", [
        ("Employeur", application.employer_name),
        ("Type de contrat", application.get_contract_type_display() if application.contract_type else ""),
        ("Salaire domicilié", _yes(application.salary_domiciliation) if application.employer_name or application.contract_type else ""),
        ("Personnes à charge", application.dependents_count or ""),
    ])
    add("Relation bancaire", [
        ("Compte du client", application.client_account_number),
        ("Début de relation", _date(application.relationship_start_date) if application.relationship_start_date else ""),
        ("Mouvements créditeurs mensuels moyens", application.avg_monthly_credit_movements),
    ])
    add("Assurance", [
        ("Assurance crédit", _yes(application.has_credit_insurance) if application.has_credit_insurance or application.insurance_company else ""),
        ("Compagnie", application.insurance_company),
        ("Prime", application.insurance_premium),
        ("Police", application.insurance_policy_number),
        ("Fin de couverture", _date(application.insurance_expiry_date) if application.insurance_expiry_date else ""),
    ])
    add("Conditions particulières", [
        ("Conditions particulières", application.special_conditions),
        ("Conditions suspensives", application.suspensive_conditions),
    ])
    add("Conformité", [
        ("Bénéficiaire effectif", application.beneficial_owner),
        ("Personne politiquement exposée", _yes(application.is_pep) if application.is_pep or application.beneficial_owner or application.funds_origin else ""),
        ("Origine des fonds", application.funds_origin),
    ])
    return blocks


def _analyses(application, currency: str) -> list[dict]:
    analyses = []
    for item in application.financial_analyses.all().order_by("created_at"):
        rows = [
            ("Période de référence", item.get_reference_period_display()),
            ("Profil", item.get_individual_profile_display() if item.individual_profile else {
                "INDIVIDUAL": "Particulier",
                "CORPORATE": "Entreprise",
                "PROFESSIONAL": "Groupement",
            }.get(item.client_type, item.client_type or "—")),
            ("Recommandation", item.get_recommendation_display() if item.recommendation else "—"),
            ("Taux d'endettement", _rate(item.debt_ratio) if item.debt_ratio is not None else "—"),
            ("DSCR", _text(item.dscr)),
            ("Endettement sous stress", _rate(item.debt_ratio_stress) if item.debt_ratio_stress is not None else "—"),
            ("DSCR sous stress", _text(item.dscr_stress)),
        ]
        money_fields = [
            ("salary_income", "Salaire net"),
            ("spouse_income", "Revenus du conjoint"),
            ("rental_income", "Loyers"),
            ("pension_income", "Pension"),
            ("other_income", "Autres revenus"),
            ("turnover", "Chiffre d'affaires"),
            ("gross_margin", "Marge brute"),
            ("ebe", "EBE"),
            ("net_result", "Résultat"),
            ("cash_flow", "Capacité d'autofinancement reconstituée"),
            ("total_assets", "Total actif"),
            ("total_debts", "Total dettes"),
            ("equity", "Fonds propres"),
            ("ongoing_credit_balance", "Encours financier"),
            ("activity_turnover", "Recettes d'activité"),
            ("activity_expenses", "Charges d'activité"),
        ]
        for attr, label in money_fields:
            try:
                value = getattr(item, attr, None)
            except Exception:
                value = None
            if value not in (None, "", 0, Decimal("0")):
                rows.append((label, _money(value, currency)))
        if item.strengths:
            rows.append(("Points forts", item.strengths))
        if item.weaknesses:
            rows.append(("Points de vigilance", item.weaknesses))
        if item.recommended_conditions:
            rows.append(("Conditions proposées", item.recommended_conditions))
        if item.comment:
            rows.append(("Avis de l'analyste", item.comment))
        rows.extend(_tpe_rows(item, currency))
        analyses.append({
            "title": f"Analyse du {_date(item.created_at)}",
            "rows": rows,
            "tables": _comparison_tables(item, currency),
        })
    return analyses


def _guarantees(application, currency: str) -> list[tuple]:
    rows = []
    for item in application.guarantees.all().order_by("created_at"):
        owner = " ".join(
            part for part in (item.owner_first_name, item.owner_last_name) if part
        ) or item.owners or "—"
        rows.append((
            item.reference or "—",
            item.get_guarantee_type_display(),
            item.get_status_display(),
            _money(item.current_value or item.expertise_value, currency),
            owner,
            (item.description or item.address or "—")[:240],
        ))
    return rows


def _sureties(application, currency: str) -> list[tuple]:
    from apps.sureties.models import SuretyEngagement

    rows = []
    engagements = SuretyEngagement.objects.filter(application=application).select_related("surety")
    for item in engagements:
        name = item.surety.display_name if item.surety_id else "—"
        rows.append((
            name,
            _money(item.amount, currency),
            item.get_status_display(),
        ))
    return rows


def _documents(application) -> list[tuple[str, str, str]]:
    rows = []
    checklist = application.document_checklist or []
    if isinstance(checklist, list):
        for item in checklist:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip()
            if not label:
                continue
            state = "Fournie" if item.get("provided") is True else "Non fournie"
            rows.append((label, "Checklist", state))
    if application.request_letter_scan:
        rows.append(("Lettre de demande", "Scan", _file_name(application.request_letter_scan)))
    for photo in application.stock_photos.all():
        rows.append((photo.caption or "Photo", "Photo", _file_name(photo.image)))
    for doc in application.documents.all():
        rows.append((doc.label or "Pièce", "Document", _file_name(doc.file)))
    return rows


def _file_name(field) -> str:
    name = getattr(field, "name", "") or ""
    return name.replace("\\", "/").split("/")[-1] or "fichier"


def _schedule(application, currency: str) -> dict:
    from apps.credits.amounts import reference_amount
    from apps.credits.models import Loan
    from apps.credits.services import compute_amortization_schedule

    try:
        loan = application.loan
    except Loan.DoesNotExist:
        loan = None
    if loan is not None and loan.installments.exists():
        rows = [
            (
                str(item.number),
                _date(item.due_date),
                _money(item.principal_due, currency),
                _money(item.interest_due, currency),
                _money(item.total_due, currency),
                item.get_status_display(),
            )
            for item in loan.installments.all()
        ]
        return {"title": "Échéancier du prêt", "rows": rows, "note": "", "last": "Statut"}

    principal = application.amount_approved or reference_amount(application) or application.amount_requested
    if not principal or not application.duration_months:
        return {"title": "Échéancier", "rows": [], "note": "Les conditions ne permettent pas encore de calculer un échéancier.", "last": "Reste dû"}
    try:
        computed = compute_amortization_schedule(
            principal,
            application.interest_rate or 0,
            application.duration_months,
            periodicity=application.periodicity,
            first_due_date=application.first_due_date,
            savings_rate=application.mandatory_savings_rate or 0,
            mechanism=application.repayment_mechanism,
            tenant_id=application.tenant_id,
        )
    except Exception:
        return {"title": "Échéancier", "rows": [], "note": "L'échéancier n'a pas pu être calculé.", "last": "Reste dû"}
    rows = [
        (
            str(item["number"]),
            _date(item["due_date"]),
            _money(item["principal"], currency),
            _money(item["interest"], currency),
            _money(item["total"], currency),
            _money(item["balance"], currency),
        )
        for item in computed
    ]
    return {
        "title": "Échéancier prévisionnel",
        "rows": rows,
        "note": "Calculé à partir des conditions actuelles du dossier. Il sera figé à la mise en place.",
        "last": "Reste dû",
    }


def _exposure(application, user, currency: str) -> dict | None:
    if user is None or not user.has_perm("credits.view_creditexposureobservation"):
        return None
    from apps.clients.models import Client
    from apps.common.access import apply_data_scope
    from apps.credits.exposure import exposure_assessment

    try:
        result = exposure_assessment(application)
    except Exception:
        return {"rows": [], "note": "Les engagements n'ont pas pu être consolidés.", "failures": []}
    visible = {
        str(pk)
        for pk in apply_data_scope(
            Client.all_tenants.filter(tenant_id=application.tenant_id),
            user,
        ).values_list("pk", flat=True)
    }
    names = {
        str(pk): name
        for pk, name in Client.all_tenants.filter(
            tenant_id=application.tenant_id
        ).values_list("pk", "company_name")
    }
    rows = []
    for row in result.get("members") or []:
        if row["client"] not in visible:
            continue
        client = Client.all_tenants.filter(pk=row["client"]).first()
        label = client.display_name if client else names.get(row["client"], "Client")
        rows.append((
            label,
            _money(row.get("external_total"), currency) if row.get("external_total") is not None else "—",
            _money(row.get("pending_total"), currency),
            _money(row.get("total"), currency) if row.get("total") is not None else "—",
            " ; ".join(row.get("issues") or []) or "—",
        ))
    return {
        "rows": rows,
        "note": result.get("note") or "",
        "failures": result.get("failures") or [],
        "client_total": result.get("client_total"),
        "group_total": result.get("group_total"),
        "currency": result.get("currency") or currency,
    }


def _logo_bytes(tenant) -> bytes | None:
    logo = getattr(tenant, "logo", None)
    if logo is None or not getattr(logo, "name", ""):
        return None
    try:
        logo.open("rb")
        raw = logo.read()
    except Exception:
        return None
    finally:
        try:
            logo.close()
        except Exception:
            pass
    try:
        from PIL import Image

        image = Image.open(io.BytesIO(raw))
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA")
        out = io.BytesIO()
        image.save(out, format="PNG")
        return out.getvalue()
    except Exception:
        return None


def _render(data: dict, brand: dict, font: str, font_b: str) -> bytes:
    from reportlab.lib.colors import white
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
        KeepTogether,
    )

    primary = _color(brand["primary"])
    secondary = _color(brand["secondary"])
    accent = _color(brand["accent"])
    sidebar = _color(brand["sidebar"])
    sidebar_text = _color(brand["sidebar_text"])
    body = _color("#17231f")
    muted = _color("#5c6b66")
    line = _color("#dce5e0")
    soft = _color("#f4f7f5")
    header_ink = _color(readable_text(brand["primary"], "#ffffff"))

    styles = {
        "h1": ParagraphStyle("h1", fontName=font_b, fontSize=16, leading=20, textColor=body),
        "meta": ParagraphStyle("meta", fontName=font, fontSize=9, leading=12, textColor=muted),
        "section": ParagraphStyle("section", fontName=font_b, fontSize=12, leading=15, textColor=primary, spaceBefore=2),
        "body": ParagraphStyle("body", fontName=font, fontSize=9, leading=12, textColor=body, alignment=TA_LEFT),
        "small": ParagraphStyle("small", fontName=font, fontSize=8, leading=10, textColor=body),
        "small_b": ParagraphStyle("small_b", fontName=font_b, fontSize=8, leading=10, textColor=header_ink),
        "note": ParagraphStyle("note", fontName=font, fontSize=8, leading=11, textColor=muted),
    }

    def para(text, style="body"):
        safe = escape(_text(text) if text is not None else "—").replace("\n", "<br/>")
        return Paragraph(safe, styles[style])

    def section(title):
        band = Table(
            [[Paragraph(escape(title), styles["section"])]],
            colWidths=[174 * mm],
        )
        band.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (-1, -1), 1.5, accent),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
        ]))
        return band

    def kv(pairs):
        if not pairs:
            return para("Aucune information enregistrée.", "note")
        rows = [[para(label, "small"), para(value, "small")] for label, value in pairs]
        table = Table(rows, colWidths=[58 * mm, 116 * mm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), soft),
            ("TEXTCOLOR", (0, 0), (-1, -1), body),
            ("FONTNAME", (0, 0), (-1, -1), font),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.3, line),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        return table

    def grid(headers, rows, widths):
        if not rows:
            return para("Aucune information enregistrée.", "note")
        head = [Paragraph(escape(item), styles["small_b"]) for item in headers]
        body_rows = [[para(cell, "small") for cell in row] for row in rows]
        table = Table([head, *body_rows], colWidths=widths, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), primary),
            ("TEXTCOLOR", (0, 0), (-1, 0), header_ink),
            ("FONTNAME", (0, 0), (-1, 0), font_b),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.3, line),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, soft]),
        ]))
        return table

    story = []
    story.append(Paragraph(escape(data["client_name"]), styles["h1"]))
    story.append(Spacer(1, 2))
    story.append(Paragraph(
        escape(f"Dossier {data['reference']} · {data['status']} · {data['headline_amount']}"),
        styles["meta"],
    ))
    story.append(Paragraph(
        escape(f"Généré le {data['generated_at']}"),
        styles["note"],
    ))
    story.append(Spacer(1, 8))

    blocks = [
        ("1. Synthèse du dossier", kv(data["identity"])),
    ]
    if data["fees"]:
        blocks.append(("Frais additionnels", grid(
            ["Intitulé", "Valeur"],
            data["fees"],
            [110 * mm, 64 * mm],
        )))
    blocks.append(("2. Profil du client", kv(data["client_rows"])))
    for title, pairs in data["profile_blocks"]:
        blocks.append((title, kv(pairs)))
    if data["analyses"]:
        parts = []
        for analysis in data["analyses"]:
            parts.append(Paragraph(escape(analysis["title"]), styles["body"]))
            parts.append(Spacer(1, 3))
            parts.append(kv(analysis["rows"]))
            for table in analysis.get("tables") or []:
                parts.append(Spacer(1, 4))
                parts.append(Paragraph(escape(table["title"]), styles["small_b"]))
                parts.append(Spacer(1, 2))
                parts.append(grid(
                    table["headers"],
                    table["rows"],
                    [width * mm for width in table["widths"]],
                ))
            parts.append(Spacer(1, 6))
        blocks.append(("3. Analyse financière", parts))
    else:
        blocks.append(("3. Analyse financière", para("Aucune analyse enregistrée.", "note")))
    blocks.append(("4. Garanties", grid(
        ["Référence", "Type", "Statut", "Valeur", "Propriétaire", "Description"],
        data["guarantees"],
        [24 * mm, 32 * mm, 22 * mm, 28 * mm, 28 * mm, 40 * mm],
    )))
    blocks.append(("5. Cautions", grid(
        ["Caution", "Montant engagé", "Statut"],
        data["sureties"],
        [80 * mm, 50 * mm, 44 * mm],
    )))
    if data["exposure"] is not None:
        exposure = data["exposure"]
        parts = []
        if exposure.get("client_total") is not None or exposure.get("group_total") is not None:
            parts.append(kv([
                ("Total client", _money(exposure.get("client_total"), exposure.get("currency"))),
                ("Total du groupe lié", _money(exposure.get("group_total"), exposure.get("currency"))),
            ]))
            parts.append(Spacer(1, 4))
        parts.append(grid(
            ["Personne", "Externe", "En circuit", "Total", "Points d'attention"],
            exposure.get("rows") or [],
            [40 * mm, 28 * mm, 28 * mm, 28 * mm, 50 * mm],
        ))
        if exposure.get("failures"):
            parts.append(Spacer(1, 4))
            parts.append(para(" ; ".join(exposure["failures"]), "note"))
        if exposure.get("note"):
            parts.append(para(exposure["note"], "note"))
        blocks.append(("6. Engagements", parts))
    schedule = data["schedule"]
    parts = []
    if schedule.get("note"):
        parts.append(para(schedule["note"], "note"))
        parts.append(Spacer(1, 4))
    parts.append(grid(
        ["N°", "Échéance", "Capital", "Intérêts", "Total", schedule.get("last") or "Reste dû"],
        schedule.get("rows") or [],
        [14 * mm, 28 * mm, 32 * mm, 30 * mm, 34 * mm, 36 * mm],
    ))
    blocks.append(("7. " + schedule["title"], parts))
    if data["loan_rows"] or any(value != "—" for _, value in data["cbs_rows"]):
        parts = []
        if data["loan_rows"]:
            parts.append(kv(data["loan_rows"]))
            parts.append(Spacer(1, 4))
        parts.append(kv(data["cbs_rows"]))
        blocks.append(("Mise en place et références CBS", parts))
    blocks.append(("8. Visites terrain", grid(
        ["Date", "Auteur", "Profil", "Lieu", "Compte rendu"],
        data["visits"],
        [24 * mm, 32 * mm, 28 * mm, 30 * mm, 60 * mm],
    )))
    blocks.append(("9. Pièces du dossier", grid(
        ["Libellé", "Nature", "État ou fichier"],
        data["documents"],
        [70 * mm, 34 * mm, 70 * mm],
    )))
    blocks.append(("10. Contrats", grid(
        ["Contrat", "Statut", "Généré le", "Par", "Signé le"],
        data["contracts"],
        [50 * mm, 28 * mm, 32 * mm, 32 * mm, 32 * mm],
    )))
    if data["conditions"]:
        blocks.append(("Réserves", grid(
            ["Statut", "Réserve", "Émise par"],
            data["conditions"],
            [36 * mm, 96 * mm, 42 * mm],
        )))
    blocks.append(("11. Circuit d'approbation", grid(
        ["Étape", "Décision", "Avis", "Acteur", "Date", "Commentaire"],
        data["decisions"],
        [32 * mm, 24 * mm, 28 * mm, 28 * mm, 28 * mm, 34 * mm],
    )))
    blocks.append(("12. Historique", grid(
        ["Date", "Événement", "Acteur", "Détail"],
        data["history"],
        [32 * mm, 36 * mm, 40 * mm, 66 * mm],
    )))

    for title, flowable in blocks:
        story.append(KeepTogether([section(title), Spacer(1, 4)]))
        if isinstance(flowable, list):
            story.extend(flowable)
        else:
            story.append(flowable)
        story.append(Spacer(1, 6))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=22 * mm,
        bottomMargin=16 * mm,
        title=f"Dossier {data['reference']}",
        author=data["filiale"],
    )
    logo_bytes = data.get("logo")

    def paint(canvas, doc_):
        canvas.saveState()
        width, height = A4
        canvas.setFillColor(sidebar)
        canvas.rect(0, height - 16 * mm, width, 16 * mm, fill=1, stroke=0)
        canvas.setFillColor(accent)
        canvas.rect(0, height - 17.2 * mm, width, 1.2 * mm, fill=1, stroke=0)
        text_x = 16 * mm
        if logo_bytes:
            try:
                from reportlab.lib.utils import ImageReader

                reader = ImageReader(io.BytesIO(logo_bytes))
                canvas.drawImage(
                    reader,
                    12 * mm,
                    height - 14.2 * mm,
                    width=12 * mm,
                    height=10 * mm,
                    preserveAspectRatio=True,
                    mask="auto",
                    anchor="w",
                )
                text_x = 26 * mm
            except Exception:
                text_x = 16 * mm
        canvas.setFillColor(sidebar_text)
        canvas.setFont(font_b, 10)
        canvas.drawString(text_x, height - 8 * mm, data["filiale"][:70])
        canvas.setFont(font, 8)
        canvas.drawRightString(width - 16 * mm, height - 8 * mm, "Dossier de crédit")
        if data.get("filiale_meta"):
            canvas.setFont(font, 7)
            canvas.drawString(text_x, height - 12.2 * mm, data["filiale_meta"][:110])
        canvas.setFillColor(secondary)
        canvas.rect(0, 0, width, 10 * mm, fill=1, stroke=0)
        canvas.setFillColor(sidebar_text)
        canvas.setFont(font, 8)
        canvas.drawString(16 * mm, 4 * mm, f"{data['filiale']} · document interne · {data['reference']}")
        canvas.drawRightString(width - 16 * mm, 4 * mm, f"Page {doc_.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=paint, onLaterPages=paint)
    return buffer.getvalue()
