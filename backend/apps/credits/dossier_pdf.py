"""Export PDF d'un dossier de crédit, à la charte de la filiale.

Les pièces jointes sont inventoriées (nom, type, date). Leurs fichiers
ne sont pas fusionnés dans le document.
"""
from __future__ import annotations

import io
import os
from datetime import date
from decimal import Decimal, InvalidOperation
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


def _tint(hex_value: str, strength: float = 0.08):
    """Mélange une couleur de la filiale avec le blanc."""
    from reportlab.lib.colors import Color

    raw = hex_value.lstrip("#")
    channels = [int(raw[index:index + 2], 16) for index in (0, 2, 4)]
    mixed = [channel + (255 - channel) * (1 - strength) for channel in channels]
    return Color(*(value / 255 for value in mixed))


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


def _referential_label(application, code, model, choices) -> str:
    """Libellé CBS du code, sinon le libellé historique du parcours."""
    raw = "" if code is None else str(code).strip()
    if not raw:
        return "—"
    label = ""
    if getattr(application, "tenant_id", None):
        try:
            from apps.catalog.cbs_resolve import resolve_ref

            label = (resolve_ref(model, application.tenant_id, raw).get("label") or "").strip()
        except Exception:
            label = ""
    return label or dict(choices).get(raw) or raw


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
    from apps.catalog.models import Currency, LoanPeriodicity, RepaymentMethod
    from apps.contracts.models import GeneratedContract
    from apps.credits.amounts import reference_amount
    from apps.credits.models import Loan, Periodicity, RepaymentMechanism
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
        ("Périodicité", _referential_label(
            application, application.periodicity, LoanPeriodicity, Periodicity.choices,
        )),
        ("Mécanisme", _referential_label(
            application, application.repayment_mechanism, RepaymentMethod, RepaymentMechanism.choices,
        )),
        ("Taux d'intérêt", _rate(application.interest_rate)),
        ("Frais de dossier", _rate(application.fees_rate)),
        ("Épargne obligatoire", "—" if application.mandatory_savings_rate in (None, "") else f"{application.mandatory_savings_rate} % du capital à chaque échéance"),
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
    profile_blocks = _profile_blocks(application, currency)
    if application.stock_photos.exists():
        photo_target = "applicant" if client is not None and getattr(client, "client_type", "") == "INDIVIDUAL" else "activity"
        profile_blocks[photo_target].append((
            "Photos du stock",
            str(application.stock_photos.count()),
        ))
    terms = _kept_rows([
        ("Montant demandé", _money(application.amount_requested, currency) if _filled(application.amount_requested) else ""),
        ("Montant proposé", _money(application.amount_proposed, currency) if _filled(application.amount_proposed) else ""),
        ("Montant accordé", _money(application.amount_approved, currency) if _filled(application.amount_approved) else ""),
        ("Devise", _referential_label(application, application.currency, Currency, ())),
        ("Taux d'intérêt", _rate(application.interest_rate) if _filled(application.interest_rate) else ""),
        ("Épargne obligatoire", "" if not application.mandatory_savings_rate else f"{application.mandatory_savings_rate} % du capital à chaque échéance"),
        ("Périodicité", _referential_label(application, application.periodicity, LoanPeriodicity, Periodicity.choices)),
        ("Durée", f"{application.duration_months} mois" if application.duration_months else ""),
        ("Première échéance", _date(application.first_due_date) if application.first_due_date else ""),
        ("Dernière échéance", _date(application.last_due_date) if application.last_due_date else ""),
        ("Mécanisme", _referential_label(application, application.repayment_mechanism, RepaymentMethod, RepaymentMechanism.choices)),
        ("Objet du financement", application.get_purpose_type_display() if application.purpose_type else ""),
        ("Objet de financement CBS", getattr(financing, "label", "") or ""),
        ("Niveau de risque", str(application.risk_level) if application.risk_level else ""),
        ("Frais de dossier", _rate(application.fees_rate) if application.fees_rate else ""),
        ("Détails de la demande", application.purpose),
    ])
    analyses = _analyses(application, currency)
    guarantees = _guarantees(application, currency)
    sureties = _sureties(application, currency)
    from .models import FieldVisit

    place_labels = dict(FieldVisit.Place.choices)
    visits = []
    for visit in application.field_visits.select_related("visited_by").prefetch_related("photos").all():
        places = ", ".join(
            place_labels.get(code, code) for code in (visit.visited_places or [])
        )
        if visit.geo_coordinates:
            places = f"{places} ({visit.geo_coordinates})" if places else visit.geo_coordinates
        author = _person(visit.visited_by)
        if visit.visitor_role:
            author = f"{author} — {visit.visitor_role}"
        report = visit.report or "—"
        photo_count = len(visit.photos.all())
        if photo_count:
            report = f"{report} — {photo_count} photo{'s' if photo_count > 1 else ''}"
        if visit.minutes:
            report = f"{report} — PV joint"
        visits.append((
            _date(visit.visit_date),
            author,
            places or "—",
            visit.get_person_met_display() if visit.person_met else "—",
            visit.get_conclusion_display() if visit.conclusion else "—",
            report,
        ))
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
        "product_label": getattr(product, "label", "") or "—",
        "agency_label": f"{agency.code} — {agency.name}" if agency else "—",
        "is_individual": getattr(client, "client_type", "") == "INDIVIDUAL",
        "generated_at": timezone.localtime(timezone.now()).strftime("%d/%m/%Y à %H:%M"),
        "terms": terms,
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


def _quantity_text(value) -> str:
    if value is None:
        return "—"
    if value == value.to_integral_value():
        return f"{int(value):,}".replace(",", " ")
    text = f"{value.quantize(Decimal('0.0001')):f}".rstrip("0").rstrip(".")
    whole, _, fraction = text.partition(".")
    body = f"{int(whole):,}".replace(",", " ") if whole.lstrip("-").isdigit() else whole
    return body if not fraction else f"{body},{fraction}"


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


def _dated_period_tables(currency, periods, mode, reading, title, indicator_title, amount_header, total_label, average_label, monthly_label):
    period_labels = {"DAY": "Journalière", "WEEK": "Hebdomadaire", "MONTH": "Mensuelle", "SEMESTER": "Semestrielle"}
    appreciation_labels = {"FAIBLE": "Faible", "MOYENNE": "Moyenne", "BONNE": "Bonne"}
    if not isinstance(periods, list) or not periods:
        return []
    daily = mode == "DAY"

    def shown_day(value):
        text = str(value or "")
        try:
            return date.fromisoformat(text).strftime("%d/%m/%Y")
        except ValueError:
            return text or "—"

    period_rows = []
    for row in periods:
        if not isinstance(row, dict):
            continue
        amount = row.get("amount")
        shown_amount = "—" if amount in (None, "") else _money(amount, currency)
        note = appreciation_labels.get(str(row.get("appreciation") or ""), "—")
        if daily:
            period_rows.append((shown_day(row.get("date")), shown_amount, note))
        else:
            period_rows.append((shown_day(row.get("start")), shown_day(row.get("end")), shown_amount, note))
    if not period_rows:
        return []

    def shown(value, money=False):
        if value in (None, ""):
            return "—"
        return _money(value, currency) if money else str(value)

    def span(label, amount):
        if not label:
            return "—"
        parts = [shown_day(part.strip()) for part in str(label).split("–")]
        return f"{' – '.join(parts)} · {shown(amount, money=True)}"

    return [
        {
            "title": title,
            "headers": ["Date", amount_header, "Appréciation"] if daily else ["Début", "Fin", amount_header, "Appréciation"],
            "rows": period_rows,
            "widths": [40, 55, 45] if daily else [32, 32, 50, 40],
        },
        {
            "title": indicator_title,
            "headers": ["Indicateur", "Valeur"],
            "rows": [
                ("Période", period_labels.get(mode, "—")),
                ("Nombre de périodes", shown(reading["count"])),
                (total_label, shown(reading["total"], money=True)),
                (average_label, shown(reading["average"], money=True)),
                ("Jours couverts", shown(reading["days"])),
                (monthly_label, shown(reading["monthly"], money=True)),
                ("Période la plus élevée", span(reading["high_label"], reading["high_amount"])),
                ("Période la plus faible", span(reading["low_label"], reading["low_amount"])),
                ("Appréciation dominante", reading["appreciation"] or "—"),
            ],
            "widths": [90, 84],
        },
    ]


def _comparison_tables(item, currency: str) -> list[dict]:
    """États comparatifs calculés à l'export, sans traiter une case vide comme zéro."""
    tables = []
    activity_comparison = item.is_individual and item.has_side_activity
    current_turnover = _optional_decimal(item.activity_turnover if activity_comparison else item.turnover)
    previous_turnover = _optional_decimal(item.turnover_prev)
    current_result = _optional_decimal(item.activity_net if activity_comparison else item.net_result)
    previous_result = _optional_decimal(item.net_result_prev)
    turnover_label = "Chiffre d'affaires de l'activité" if activity_comparison else "Chiffre d'affaires"
    result_label = "Résultat de l'activité" if activity_comparison else "Résultat net"
    statement = []
    def _stated(current, previous):
        return any(value not in (None, Decimal("0")) for value in (current, previous))

    if _stated(current_turnover, previous_turnover):
        statement.append((
            turnover_label, _money(current_turnover, currency), _money(previous_turnover, currency),
            _spread_text(current_turnover, previous_turnover, currency), _variation_text(current_turnover, previous_turnover),
        ))
    if _stated(current_result, previous_result):
        statement.append((
            result_label, _money(current_result, currency), _money(previous_result, currency),
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
    from apps.credits.analysis_details import product_line_figures, product_nature
    nature_label = {"RESOLD": "Revendu", "MANUFACTURED": "Fabriqué", "SERVICE": "Service"}
    for row in products:
        if not isinstance(row, dict):
            continue
        if not (row.get("name") or row.get("sale_price") or row.get("unit_cost") or row.get("quantity") or row.get("quantity_produced") or row.get("material_cost") or row.get("nature") in {"MANUFACTURED", "SERVICE"}):
            continue
        figures = product_line_figures(row)
        nature = product_nature(row)
        sold = _optional_decimal(row.get("quantity"))
        produced = _optional_decimal(row.get("quantity_produced")) if nature == "MANUFACTURED" else None
        unit = figures["unit_cost"]
        unit_text = "Aucun" if nature == "SERVICE" and row.get("unit_cost") in (None, "") else _money(unit, currency)
        product_rows.append((
            nature_label.get(nature, "Revendu"),
            str(row.get("name") or "—"),
            str(row.get("unit") or "—"),
            _quantity_text(produced),
            _quantity_text(sold),
            unit_text,
            _money(_optional_decimal(row.get("sale_price")), currency),
            _money(figures["sales"], currency),
            _money(figures["margin"], currency),
        ))
    if product_rows:
        tables.append({
            "title": "Fiches produits — le chiffre d'affaires retenu est la quantité vendue",
            "headers": ["Nature", "Article", "Unité", "Produite", "Vendue", "Coût unit.", "Prix", "CA retenu", "Marge"],
            "rows": product_rows,
            "widths": [18, 28, 14, 16, 16, 20, 20, 22, 20],
        })
    stock_labels = (
        ("production_stock_materials", "Matières premières"),
        ("production_stock_wip", "En-cours"),
        ("production_stock_finished", "Produits finis"),
    )
    production_stocks = [(label, _money(_optional_decimal(details.get(key)), currency)) for key, label in stock_labels if details.get(key) not in (None, "")]
    if production_stocks:
        tables.append({
            "title": "Stocks de production à la date d'arrêté",
            "headers": ["Stock", "Valeur"],
            "rows": production_stocks,
            "widths": [110, 64],
        })
    identity_labels = (
        ("production_main_products", "Produits fabriqués"),
        ("production_process", "Procédé"),
        ("production_capacity", "Capacité installée"),
        ("production_utilization", "Capacité utilisée"),
        ("production_main_material", "Matière principale"),
        ("production_other_inputs", "Autres intrants"),
        ("production_workshop", "Atelier et équipement"),
        ("production_workforce", "Main-d'œuvre de production"),
        ("production_quality", "Qualité et rebuts"),
        ("production_comment", "Réserves"),
    )
    identity_rows = [(label, str(details.get(key))) for key, label in identity_labels if isinstance(details.get(key), str) and details.get(key).strip()]
    if identity_rows or details.get("manufactures") == "yes":
        if not identity_rows:
            identity_rows = [("Identité", "Production déclarée, fiche non renseignée")]
        tables.append({
            "title": "Identité de la production",
            "headers": ["Rubrique", "Élément"],
            "rows": identity_rows,
            "widths": [58, 116],
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
    suppliers = details.get("suppliers") if isinstance(details.get("suppliers"), list) else []
    supplier_rows = []
    payment_modes = {"CASH": "Comptant", "CREDIT": "À crédit"}
    for row in suppliers:
        if not isinstance(row, dict):
            continue
        if not any(str(row.get(field) or "").strip() for field in ("name", "place", "product", "share", "amount", "payment_mode", "delay_days")):
            continue
        share = row.get("share")
        amount = row.get("amount")
        delay = row.get("delay_days")
        supplier_rows.append((
            str(row.get("name") or "—"),
            str(row.get("place") or "—"),
            str(row.get("product") or "—"),
            "—" if share in (None, "") else f"{share} %",
            "—" if amount in (None, "") else _money(amount, currency),
            payment_modes.get(str(row.get("payment_mode") or ""), "—"),
            "—" if delay in (None, "") else f"{delay} j",
        ))
    if supplier_rows:
        tables.append({
            "title": "Fournisseurs",
            "headers": ["Nom", "Lieu", "Produit", "Part", "Montant", "Paiement", "Délai"],
            "rows": supplier_rows,
            "widths": [32, 28, 28, 18, 28, 22, 18],
        })
    history = details.get("purchase_history") if isinstance(details.get("purchase_history"), list) else []
    history_rows = []
    for row in history:
        if not isinstance(row, dict):
            continue
        quantity = _optional_decimal(row.get("quantity"))
        price = _optional_decimal(row.get("unit_price"))
        amount = None if quantity is None or price is None else quantity * price
        if not any(str(row.get(field) or "").strip() for field in ("date", "product", "supplier", "quantity", "unit", "unit_price")):
            continue
        history_rows.append((
            str(row.get("date") or "—"),
            str(row.get("product") or "—"),
            str(row.get("supplier") or "—"),
            "—" if quantity is None else f"{quantity:,.2f}".replace(",", " ").replace(".", ","),
            str(row.get("unit") or "—"),
            "—" if price is None else _money(price, currency),
            "—" if amount is None else _money(amount, currency),
        ))
    if history_rows:
        period = " — ".join(part for part in (str(details.get("purchase_period_start") or ""), str(details.get("purchase_period_end") or "")) if part)
        tables.append({
            "title": f"Historique des achats{f' ({period})' if period else ''}",
            "headers": ["Date", "Produit", "Fournisseur", "Quantité", "Unité", "Prix", "Montant"],
            "rows": history_rows,
            "widths": [24, 32, 32, 22, 16, 24, 24],
        })
        from apps.credits.analysis_details import purchase_history_indicators, purchase_monthly_total
        indicators = purchase_history_indicators(details)
        monthly_purchases = purchase_monthly_total(details)
        def shown(value, money=False):
            if value in (None, ""):
                return "—"
            return _money(value, currency) if money else str(value)
        last = "—"
        if indicators["last_date"]:
            last = f"{indicators['last_date']} · {shown(indicators['last_amount'], money=True)}"
        main = indicators["main_supplier"] or "—"
        if indicators["main_supplier"] and indicators["main_share"] is not None:
            main = f"{indicators['main_supplier']} · {indicators['main_share']} %"
        tables.append({
            "title": "Indicateurs des achats",
            "headers": ["Indicateur", "Valeur"],
            "rows": [
                ("Achats de la période", shown(indicators["total"], money=True)),
                ("Nombre d'achats", shown(indicators["count"])),
                ("Achat moyen", shown(indicators["average"], money=True)),
                ("Approvisionnements par mois", shown(indicators["per_month"])),
                *( [("Achats du mois", shown(monthly_purchases, money=True))] if monthly_purchases is not None else [] ),
                ("Dernier achat de la période", last),
                ("Nombre de fournisseurs", shown(indicators["supplier_count"])),
                ("Principal fournisseur", main),
            ],
            "widths": [90, 84],
        })
    payments = details.get("supplier_payments") if isinstance(details.get("supplier_payments"), list) else []
    payment_rows = []
    for row in payments:
        if not isinstance(row, dict):
            continue
        if not any(str(row.get(field) or "").strip() for field in ("date", "supplier", "amount", "payment_mode")):
            continue
        amount = row.get("amount")
        payment_rows.append((
            str(row.get("date") or "—"),
            str(row.get("supplier") or "—"),
            "—" if amount in (None, "") else _money(amount, currency),
            {"CASH": "Espèces", "MOBILE": "Mobile Money", "TRANSFER": "Virement", "CHEQUE": "Chèque"}.get(str(row.get("payment_mode") or ""), "—"),
        ))
    if payment_rows:
        from apps.credits.analysis_details import supplier_payment_indicators
        paid = supplier_payment_indicators(details)
        def paid_shown(value, money=False):
            if value in (None, ""):
                return "—"
            return _money(value, currency) if money else str(value)
        last_payment = "—"
        if paid["last_date"]:
            last_payment = f"{paid['last_date']} · {paid_shown(paid['last_amount'], money=True)}"
        tables.append({
            "title": "Paiements fournisseurs",
            "headers": ["Date", "Fournisseur", "Montant", "Mode"],
            "rows": payment_rows,
            "widths": [32, 60, 40, 42],
        })
        tables.append({
            "title": "Indicateurs des paiements",
            "headers": ["Indicateur", "Valeur"],
            "rows": [
                ("Total payé", paid_shown(paid["total"], money=True)),
                ("Nombre de paiements", paid_shown(paid["count"])),
                ("Paiement moyen", paid_shown(paid["average"], money=True)),
                ("Dernier paiement", last_payment),
            ],
            "widths": [90, 84],
        })
    from apps.credits.analysis_details import (
        collection_monthly_total, collection_period_indicators, sales_monthly_total, sales_period_indicators,
    )
    rhythm_labels = {"DAY": "Jour", "WEEK": "Semaine", "MONTH": "Mois"}
    periods = details.get("sales_periods")
    shared_period = str(details.get("analysis_period_mode") or "")
    period_mode = shared_period or str(details.get("sales_period_mode") or "")
    tables.extend(_dated_period_tables(
        currency, periods, period_mode, sales_period_indicators(details),
        "Chiffre d'affaires", "Indicateurs du chiffre d'affaires",
        "Chiffre d'affaires", "Chiffre d'affaires total", "CA moyen", "CA du mois",
    ))
    collections = details.get("collection_periods")
    collection_mode = shared_period or str(details.get("collection_period_mode") or "")
    tables.extend(_dated_period_tables(
        currency, collections, collection_mode, collection_period_indicators(details),
        "Encaissements", "Indicateurs des encaissements",
        "Montant encaissé", "Total encaissé", "Encaissement moyen", "Encaissé sur le mois",
    ))
    sales_rows = []
    sales_rhythm = str(details.get("sales_rhythm") or "")
    if not (isinstance(periods, list) and periods) and (sales_rhythm in rhythm_labels or details.get("sales_amount") not in (None, "")):
        sales_rows.append(("Rythme des ventes", rhythm_labels.get(sales_rhythm, "—")))
        sales_amount = details.get("sales_amount")
        sales_rows.append(("Montant des ventes", "—" if sales_amount in (None, "") else _money(sales_amount, currency)))
        sales_month = sales_monthly_total(details)
        sales_rows.append(("CA du mois", "—" if sales_month is None else _money(sales_month, currency)))
    collection_rhythm = str(details.get("collection_rhythm") or "")
    if not (isinstance(collections, list) and collections) and (collection_rhythm in rhythm_labels or details.get("collection_amount") not in (None, "")):
        sales_rows.append(("Rythme des encaissements", rhythm_labels.get(collection_rhythm, "—")))
        collected = details.get("collection_amount")
        sales_rows.append(("Montant encaissé", "—" if collected in (None, "") else _money(collected, currency)))
        collected_month = collection_monthly_total(details)
        sales_rows.append(("Encaissé sur le mois", "—" if collected_month is None else _money(collected_month, currency)))
    if sales_rows:
        tables.append({
            "title": "Ventes et encaissements",
            "headers": ["Indicateur", "Valeur"],
            "rows": sales_rows,
            "widths": [90, 84],
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
        "tpe_purchases_invoices": "Achats mensuels selon les factures",
        "tpe_purchases_ledger": "Achats mensuels selon le cahier",
        "tpe_purchases_cost_rate": "Achats mensuels selon le taux de coût",
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
    from apps.credits.analysis_details import selected_purchase_methods
    method_labels = {
        "INVOICES": "Factures fournisseurs",
        "LEDGER": "Cahier d'achats",
        "COST_RATE": "Taux de coût issu de la marge",
        "OTHER": "Autre méthode",
    }
    application = getattr(item, "application", None)
    informal = (
        getattr(application, "tax_regime", "") == "INFORMAL"
        and not item.is_corporate
        and not item.is_groupement
        and (item.has_side_activity or item.individual_profile in {"INDEPENDANT", "MIXTE"})
    )
    document_methods = {"INVOICES", "LEDGER"} if informal else set()
    methods = [
        method_labels[code]
        for code in selected_purchase_methods(item.analysis_details or {})
        if code in method_labels and code not in document_methods
    ]
    if methods:
        rows.append(("Méthode d'achats" if len(methods) == 1 else "Méthodes d'achats", ", ".join(methods)))
    comment = _detail_text(item, "purchase_comment")
    if comment:
        rows.append(("Commentaire sur les achats", comment))
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
    address = " ".join(part for part in (client.address, client.city, client.country) if part)
    birth = getattr(client, "birth_date", None)
    rows = _kept_rows([
        ("Nom", client.display_name),
        ("Type", client.get_client_type_display()),
        ("Téléphone", client.phone),
        ("E-mail", client.email),
        ("Adresse", address),
        ("Pièce d'identité", client.national_id),
        ("Profession", getattr(client, "profession", "")),
        ("Date de naissance", _date(birth) if birth else ""),
        ("Compte", client.cbs_account_number),
        ("Identifiant CBS", client.cbs_client_id),
        ("Raison sociale", getattr(client, "company_name", "")),
        ("RCCM", getattr(client, "rccm", "")),
        ("IFU", getattr(client, "ifu", "")),
    ])
    return rows


def _kept_rows(pairs) -> list[tuple[str, str]]:
    return [(label, _text(value)) for label, value in pairs if _filled(value)]


def _profile_blocks(application, currency: str) -> dict:
    client = application.client
    applicant_identity = []
    if client is not None and getattr(client, "client_type", "") == "INDIVIDUAL":
        spouse = " ".join(
            part for part in (getattr(client, "spouse_last_name", ""), getattr(client, "spouse_first_name", "")) if part
        )
        applicant_identity = [
            ("Civilité", client.get_civility_display() if getattr(client, "civility", "") and hasattr(client, "get_civility_display") else ""),
            ("Nom", getattr(client, "last_name", "")),
            ("Prénom", getattr(client, "first_name", "")),
            ("Date de naissance", _date(client.birth_date) if getattr(client, "birth_date", None) else ""),
            ("Pays de naissance", getattr(client, "birth_country", "")),
            ("Nationalité", getattr(client, "nationality", "")),
            ("Situation matrimoniale", client.get_marital_status_display() if getattr(client, "marital_status", "") and hasattr(client, "get_marital_status_display") else ""),
            ("Conjoint", spouse),
            ("Téléphone du conjoint", getattr(client, "spouse_phone", "")),
            ("Profession du conjoint", getattr(client, "spouse_profession", "")),
        ]
    financing = []
    if application.project_total_cost not in (None, "", 0, Decimal("0")):
        financing.append(("Coût total du projet", _money(application.project_total_cost, currency)))
    if application.personal_contribution not in (None, "", 0, Decimal("0")):
        financing.append(("Apport personnel", _money(application.personal_contribution, currency)))
    if application.financed_quota not in (None, ""):
        financing.append(("Quotité financée", _rate(application.financed_quota)))
    individual = client is not None and getattr(client, "client_type", "") == "INDIVIDUAL"
    cycle = [] if individual else [
        ("Délai paiement clients", f"{application.avg_client_payment_days} j" if application.avg_client_payment_days is not None else ""),
        ("Délai paiement fournisseurs", f"{application.avg_supplier_payment_days} j" if application.avg_supplier_payment_days is not None else ""),
    ]
    commercial = [
        ("Début de l'activité", _date(application.activity_start_date) if application.activity_start_date else ""),
        ("Adresse de l'activité", application.exact_address),
        ("Clientèle", application.clientele),
        ("Régime fiscal", application.get_tax_regime_display() if application.tax_regime else ""),
        *cycle,
        ("Zone de chalandise", application.get_catchment_area_display() if application.catchment_area else ""),
    ]
    return {
        "activity": [] if individual else _kept_rows(commercial),
        "applicant": _kept_rows(applicant_identity + [
        ("Parcours", application.get_earning_path_display() if application.earning_path else ""),
        ("Régime matrimonial", application.get_marital_regime_display() if application.marital_regime else ""),
        ("Le conjoint a un revenu", _yes(application.spouse_has_income) if application.spouse_has_income is not None else ""),
        ("Enfants à charge", application.children_count if application.children_count is not None else ""),
        ("Personnes à charge", application.dependents_count if application.dependents_count is not None else ""),
        ("Logement", application.get_housing_status_display() if application.housing_status else ""),
        ("Ancienneté dans le logement (mois)", application.housing_seniority_months if application.housing_seniority_months is not None else ""),
        ("Profession", application.employment_profession),
        ("Poste occupé", application.job_title),
        ("Employeur", application.employer_name),
        ("Adresse de l'employeur", application.employer_address),
        ("Téléphone de l'employeur", application.employer_phone),
        ("Secteur de l'employeur", application.employer_sector),
        ("Type de contrat", application.get_contract_type_display() if application.contract_type else ""),
        ("Fin du contrat", _date(application.contract_end_date) if application.contract_type == "CDD" and application.contract_end_date else ""),
        ("Ancienneté dans l'emploi (mois)", application.job_seniority_months if application.job_seniority_months is not None else ""),
        ("Ancienneté professionnelle (mois)", application.career_seniority_months if application.career_seniority_months is not None else ""),
        ("Salaire domicilié", _yes(application.salary_domiciliation) if application.employer_name or application.contract_type or application.salary_domiciliation else ""),
        ("Activité", application.activity_name),
        ("Métier", application.activity_trade),
        ("Nature de l'activité", application.get_activity_nature_display() if application.activity_nature else ""),
        ("Offre principale", application.activity_offer),
        ("Secteur de l'activité", application.activity_sector),
        ("Mode d'exploitation", application.get_activity_operation_display() if application.activity_operation else ""),
        ("Approvisionnement", application.activity_supply),
        ("Local de l'activité", application.get_activity_premises_status_display() if application.activity_premises_status else ""),
        ("Autorisation d'exercer", application.get_activity_authorization_display() if application.activity_authorization else ""),
        ("Référence de l'autorisation", application.activity_authorization_ref),
        ("IFU de l'activité", "" if application.tax_regime == "INFORMAL" else application.activity_ifu),
        ("RCCM de l'activité", "" if application.tax_regime == "INFORMAL" else application.activity_rccm),
        ("NINEA", "" if application.tax_regime == "INFORMAL" else application.activity_ninea),
        ] + (commercial if individual else [])),
        "banking": _kept_rows([
            item
            for index, account in enumerate(application.external_accounts.all(), start=1)
            for item in (
                (f"{index}. Institution", account.institution_name),
                (f"{index}. Ouverture", _date(account.opened_on) if account.opened_on else ""),
                (f"{index}. Numéro de compte", account.account_number),
                (f"{index}. Mouvements créditeurs (3 mois)", account.credit_movement_count if account.credit_movement_count is not None else ""),
                (f"{index}. Volume créditeur", _money(account.credit_movement_volume, currency) if account.credit_movement_volume not in (None, "") else ""),
                (f"{index}. Relevé", "Joint" if account.statement else ""),
            )
        ]),
        "special": _kept_rows([
            ("Conditions particulières", application.special_conditions),
            ("Conditions suspensives", application.suspensive_conditions),
        ]),
        "compliance": _kept_rows(
            ([("Bénéficiaire effectif", application.beneficial_owner)] if getattr(client, "client_type", "") != "INDIVIDUAL" else [])
            + ([("Personne politiquement exposée", "Oui"), ("Explication", application.pep_details)] if application.is_pep else [])
        ),
        "financing": financing,
        "premises": application.get_premises_status_display() if application.premises_status else "",
    }


def _nonzero_money_rows(item, currency: str, fields) -> list[tuple[str, str]]:
    rows = []
    for attr, label in fields:
        try:
            value = getattr(item, attr, None)
        except Exception:
            value = None
        if value in (None, "", 0, Decimal("0")):
            continue
        rows.append((label, _money(value, currency)))
    return rows


def _detail_text(item, key: str) -> str:
    value = (item.analysis_details or {}).get(key)
    return value.strip() if isinstance(value, str) else ""


def _balance_comparison_rows(item, currency: str) -> list[tuple[str, str]]:
    from apps.credits.analysis_details import activity_balance_reading, household_patrimony_total, net_patrimony

    details = item.analysis_details or {}
    current = {
        "stock": item.activity_stock_value, "receivables": item.activity_receivables,
        "cash": item.activity_cash_available, "fixed": item.activity_fixed_assets,
        "debt": item.activity_supplier_debt,
    }
    previous = {
        "stock": details.get("activity_stock_prev"), "receivables": details.get("activity_receivables_prev"),
        "cash": details.get("activity_cash_prev"), "fixed": details.get("activity_fixed_assets_prev"),
        "debt": details.get("activity_supplier_debt_prev"),
    }
    reading = activity_balance_reading(current, previous)
    rows = []
    if reading["assets_prev"] is not None or reading["bfr_prev"] is not None or reading["net_prev"] is not None:
        for label, key in (
            ("Actif N-1", "assets_prev"), ("Variation de l'actif", "assets_variation"),
            ("BFR N-1", "bfr_prev"), ("Variation du BFR", "bfr_variation"),
            ("Situation nette N", "net"), ("Situation nette N-1", "net_prev"),
        ):
            if reading[key] is not None:
                rows.append((label, _money(reading[key], currency)))
    household = household_patrimony_total(
        details, item.personal_savings, item.personal_real_estate_value,
        item.personal_vehicle_value, item.personal_productive_assets,
    )
    combined = net_patrimony(reading["net"], household)
    if household not in (None, Decimal("0")):
        rows.append(("Patrimoine du ménage", _money(household, currency)))
    if household not in (None, Decimal("0")) and combined is not None:
        rows.append(("Patrimoine net", _money(combined, currency)))
    comment = details.get("patrimony_comment")
    if isinstance(comment, str) and comment.strip():
        rows.append(("Autres détails du patrimoine", comment.strip()))
    return rows


def _operating_charge_rows(item, currency: str) -> list[tuple[str, str]]:
    labels = (
        ("activity_charge_place", "Loyer ou droit de place"),
        ("activity_charge_staff", "Personnel et aides"),
        ("activity_charge_transport", "Transport"),
        ("activity_charge_utilities", "Eau et électricité"),
        ("activity_charge_telecom", "Téléphone"),
        ("activity_charge_maintenance", "Entretien et réparations"),
        ("activity_charge_fees", "Taxes et redevances"),
        ("activity_charge_supplies", "Emballages et consommables"),
    )
    details = item.analysis_details or {}
    rows = []
    for key, label in labels:
        amount = details.get(key)
        if amount in (None, ""):
            continue
        rows.append((label, _money(amount, currency)))
    return rows + _extra_money_rows(item, currency, "activity_extra_charges")


def _extra_money_rows(item, currency: str, key: str) -> list[tuple[str, str]]:
    rows = []
    for line in (item.analysis_details or {}).get(key) or []:
        if not isinstance(line, dict):
            continue
        label = str(line.get("label") or "").strip()
        amount = line.get("amount")
        if not label or amount in (None, ""):
            continue
        rows.append((label, _money(amount, currency)))
    return rows


def _extra_activity_rows(item, currency: str) -> list[tuple[str, str]]:
    rows = []
    for line in (item.analysis_details or {}).get("extra_activities") or []:
        if not isinstance(line, dict):
            continue
        label = str(line.get("label") or "").strip()
        turnover = line.get("turnover")
        expenses = line.get("expenses")
        if not label or (turnover in (None, "") and expenses in (None, "")):
            continue
        net = _optional_decimal(turnover) or Decimal("0")
        net -= _optional_decimal(expenses) or Decimal("0")
        rows.append((label, _money(net, currency)))
    return rows


def _metric_rows(item, currency: str) -> list[tuple[str, str]]:
    from apps.credits.analytics import compute_metrics
    from apps.credits.models import AnalysisThreshold

    try:
        thresholds = AnalysisThreshold.for_application(
            item.application, individual_profile=item.individual_profile,
        )
        metrics = compute_metrics(item, thresholds, recalculate_installment=True)
    except Exception:
        return []
    flags = metrics.get("flags") or {}

    def money(key):
        value = metrics.get(key)
        return None if value is None else _money(value, currency)

    def rate(key):
        value = metrics.get(key)
        return None if value is None else _rate(value)

    def times(key):
        value = metrics.get(key)
        return None if value is None else f"{value} ×"

    if item.is_corporate:
        pairs = [
            ("Chiffre d'affaires", money("declared_income")),
            ("DSCR global", times("global_dscr")),
            ("DSCR sous stress", times("dscr_stress")),
            ("Capacité avant nouveau crédit", money("repayment_capacity")),
            ("Échéance mensuelle", money("installment")),
            ("Marge de trésorerie après crédit", money("safety_margin")),
            ("Couverture par garanties", rate("guarantee_coverage")),
        ]
    elif item.is_groupement:
        pairs = [
            ("Recettes collectives / mois", money("collective_income")),
            ("Charges collectives / mois", money("collective_charges")),
            ("Capacité avant nouveau crédit", money("repayment_capacity")),
            ("Échéance mensuelle", money("installment")),
            ("Épargne obligatoire — équivalent mensuel", money("monthly_savings")),
            ("Effort total", money("total_cash_effort")),
            ("Marge de trésorerie après crédit", money("safety_margin")),
            ("Taux d'endettement global", rate("debt_ratio")),
            ("Taux d'endettement sous stress", rate("debt_ratio_stress")),
            ("Couverture par garanties", rate("guarantee_coverage")),
        ]
    else:
        pairs = [
            ("Revenus déclarés / mois", money("declared_income")),
            ("Revenus retenus après pondération / mois", money("weighted_income")),
            ("Charges du ménage / mois", money("household_charges_monthly")),
            ("Capacité avant nouveau crédit, dette existante déduite", money("repayment_capacity")),
            ("Équivalent mensuel de la nouvelle échéance", money("installment")),
            ("Épargne obligatoire — équivalent mensuel", money("monthly_savings")),
            ("Effort total", money("total_cash_effort")),
            ("Reste à vivre après crédit et épargne", money("safety_margin")),
            ("Effort moyen sur la durée", money("average_monthly_cash_payment")),
            ("Pic d'échéance", money("peak_cash_payment")),
            ("Taux d'endettement global", rate("debt_ratio")),
            ("Reste à vivre / personne", money("disposable_per_capita")),
            ("Croissance du CA d'activité", rate("turnover_growth")),
            ("Croissance du résultat d'activité", rate("result_growth")),
            ("Quotité cessible disponible", money("transferable_quota_available") if _dec_positive(item.net_salary) else None),
            ("Couverture par garanties", rate("guarantee_coverage")),
            ("Taux d'endettement sous stress", rate("debt_ratio_stress")),
            ("Reste disponible mensuel sous stress", money("stress_residual")),
        ]
    rows = [(label, value) for label, value in pairs if value not in (None, "")]
    if flags.get("capacity_ok") is True:
        rows.append(("Couverture de l'effort", "Effort couvert"))
    elif flags.get("capacity_ok") is False:
        rows.append(("Couverture de l'effort", "Effort non couvert"))
    rows.extend(_tpe_rows(item, currency))
    return rows


def _dec_positive(value) -> bool:
    try:
        return Decimal(str(value)) > 0
    except Exception:
        return False


def _plain_days(raw) -> str:
    try:
        number = Decimal(str(raw))
        if number == number.to_integral_value():
            return str(int(number))
    except (InvalidOperation, TypeError, ValueError):
        pass
    return str(raw)


def _observed_payment_delays(application, item) -> list[tuple[str, str]]:
    """Cycle observé de l'activité. L'analyse prime ; le profil ne sert que tant qu'elle ne l'a pas repris."""
    client = getattr(application, "client", None)
    if getattr(client, "client_type", "") != "INDIVIDUAL":
        return []
    details = item.analysis_details or {}
    rows = []
    for key, attr, label in (
        ("observed_client_payment_days", "avg_client_payment_days", "Délai moyen paiement clients"),
        ("observed_supplier_payment_days", "avg_supplier_payment_days", "Délai moyen paiement fournisseurs"),
    ):
        if key in details:
            raw = details.get(key)
            text = "" if raw in (None, "") else f"{_plain_days(raw)} j"
        else:
            raw = getattr(application, attr, None)
            text = "" if raw is None else f"{raw} j"
        if text:
            rows.append((label, text))
    return rows


def _consulted_documents(application, item) -> str:
    if (
        getattr(application, "tax_regime", "") != "INFORMAL"
        or item.is_corporate
        or item.is_groupement
        or not (item.has_side_activity or item.individual_profile in {"INDEPENDANT", "MIXTE"})
    ):
        return ""
    from apps.credits.analysis_details import selected_purchase_methods

    details = item.analysis_details or {}
    labels = []
    if item.activity_records_available:
        labels.append("Cahier de caisse")
    if details.get("consulted_sales_book") == "yes":
        labels.append("Cahier de ventes")
    if details.get("consulted_sales_invoices") == "yes":
        labels.append("Factures de vente")
    if details.get("consulted_bank_statements") == "yes":
        labels.append("Relevés bancaires ou mobile money")
    if item.stock_count_verified:
        labels.append("Inventaire de stock")
    methods = set(selected_purchase_methods(details))
    if details.get("consulted_purchase_invoices") == "yes" or (
        details.get("consulted_purchase_invoices") != "" and "INVOICES" in methods
    ):
        labels.append("Factures fournisseurs")
    if details.get("consulted_purchase_ledger") == "yes" or (
        details.get("consulted_purchase_ledger") != "" and "LEDGER" in methods
    ):
        labels.append("Cahier d'achats")
    if item.cash_position_verified:
        labels.append("Caisse et banques")
    return ", ".join(labels)


def _analyses(application, currency: str) -> list[dict]:
    analyses = []
    for item in application.financial_analyses.all().order_by("created_at"):
        profile = item.get_individual_profile_display() if item.individual_profile else {
            "INDIVIDUAL": "Particulier",
            "CORPORATE": "Entreprise",
            "PROFESSIONAL": "Groupement",
        }.get(item.client_type, item.client_type or "")
        sections = [{
            "title": "Identification",
            "rows": _kept_rows([
                ("Date d'analyse", _date(item.analysis_date) if item.analysis_date else ""),
                ("Période de référence", item.get_reference_period_display()),
                ("Profil", profile),
                ("Recommandation", item.get_recommendation_display() if item.recommendation else ""),
                ("Autres détails du contexte", _detail_text(item, "analysis_context_comment")),
            ]),
        }]
        if not item.is_corporate and not item.is_groupement:
            sections.extend([
                {"title": "Revenus du ménage", "rows": _nonzero_money_rows(item, currency, [
                    ("salary_income", "Salaire net"),
                    ("spouse_income", "Revenus du conjoint"),
                    ("rental_income", "Loyers / rentes"),
                    ("pension_income", "Pension"),
                    ("variable_income", "Primes / revenus variables"),
                    ("other_activity_income", "Revenus d'activité hors bloc dédié"),
                    ("other_income", "Autres revenus"),
                ]) + _extra_money_rows(item, currency, "extra_income") + _kept_rows([
                    ("Justificatifs des revenus", _detail_text(item, "household_income_evidence")),
                ])},
                {"title": "Charges du ménage", "rows": _nonzero_money_rows(item, currency, [
                    ("rent_expense", "Logement"),
                    ("food_expense", "Alimentation"),
                    ("utilities_expense", "Eau / électricité / téléphone"),
                    ("transport_expense", "Transport"),
                    ("education_expense", "Scolarité"),
                    ("health_expense", "Santé"),
                    ("tontine_expense", "Tontines"),
                    ("social_contributions", "Cotisations / assurances"),
                    ("family_support_expense", "Soutien familial"),
                    ("other_monthly_obligations", "Autres obligations sur la période"),
                ]) + _extra_money_rows(item, currency, "extra_charges")},
                {"title": "Emploi et stabilité", "rows": _kept_rows([
                    ("Employeur", item.employer_name),
                    ("Secteur", item.employer_sector),
                    ("Type d'emploi", item.get_employment_type_display() if item.employment_type else ""),
                    ("Ancienneté (mois)", item.employment_seniority_months if item.employment_seniority_months is not None else ""),
                    ("Retenues déjà prélevées", _money(item.salary_deductions, currency) if _dec_positive(item.salary_deductions) else ""),
                    ("Salaire domicilié / traçable", "Oui" if item.salary_paid_through_bank else ""),
                    ("Salaire vérifié", "Oui" if item.salary_verified else ""),
                    ("Perspectives de l'emploi", _detail_text(item, "employment_outlook")),
                ])},
                {"title": "Patrimoine du ménage", "rows": _nonzero_money_rows(item, currency, [
                    ("personal_savings", "Épargne disponible"),
                    ("personal_real_estate_value", "Immobilier"),
                    ("personal_vehicle_value", "Véhicules"),
                    ("personal_productive_assets", "Actifs productifs du ménage"),
                ]) + _kept_rows([
                    ("Propriété des actifs", _detail_text(item, "asset_ownership")),
                    ("Qualité des créances", _detail_text(item, "receivables_quality")),
                ])},
            ])
        elif item.is_groupement:
            sections.append({"title": "Groupement", "rows": _nonzero_money_rows(item, currency, [
                ("collective_contributions", "Cotisations"),
                ("collective_other_income", "Autres recettes"),
                ("group_activity_turnover", "CA commun"),
                ("collective_operating_expenses", "Fonctionnement"),
                ("group_activity_expenses", "Charges de l'activité"),
                ("collective_savings", "Épargne"),
            ]) + _kept_rows([
                ("Membres", item.members_count if item.members_count else ""),
                ("Cotisants actifs", item.active_contributing_members if item.active_contributing_members else ""),
                ("Commentaire", item.group_comment),
            ])})
        else:
            sections.append({"title": "Compte de résultat et bilan", "rows": _nonzero_money_rows(item, currency, [
                ("turnover", "Chiffre d'affaires"),
                ("gross_margin", "Marge brute"),
                ("ebe", "EBE"),
                ("net_result", "Résultat"),
                ("cash_flow", "Capacité d'autofinancement reconstituée"),
                ("total_assets", "Total actif"),
                ("total_debts", "Total dettes"),
                ("equity", "Fonds propres"),
                ("ongoing_credit_balance", "Encours financier"),
            ])})
        if item.has_side_activity or item.individual_profile in {"INDEPENDANT", "MIXTE"}:
            sections.append({"title": "Activité", "rows": _nonzero_money_rows(item, currency, [
                ("activity_turnover", "Recettes d'activité"),
                ("activity_expenses", "Charges d'activité"),
                ("activity_purchases", "Dont achats"),
            ]) + _operating_charge_rows(item, currency) + _nonzero_money_rows(item, currency, [
                ("activity_stock_value", "Stock"),
                ("activity_receivables", "Créances clients"),
                ("activity_cash_available", "Trésorerie de l'activité"),
                ("activity_fixed_assets", "Actifs productifs de l'activité"),
            ]) + _balance_comparison_rows(item, currency) + _kept_rows([
                ("Période d'analyse", " · ".join(part for part in (
                    " – ".join(part for part in (
                        str((item.analysis_details or {}).get("analysis_period_start") or ""),
                        str((item.analysis_details or {}).get("analysis_period_end") or ""),
                    ) if part),
                    {"DAY": "Jour", "WEEK": "Semaine", "MONTH": "Mois", "SEMESTER": "Semestre"}.get(str((item.analysis_details or {}).get("analysis_period_mode") or ""), ""),
                ) if part)),
                ("Activité", item.activity_name),
                ("Commentaire", item.activity_comment),
            ]) + _observed_payment_delays(application, item) + _extra_activity_rows(item, currency)})
        documents = [
            (doc.label or "Fichier", _file_name(doc.file))
            for doc in item.documents.all()
        ]
        sections.extend([
            {"title": "Synthèse de capacité", "rows": _metric_rows(item, currency)},
            {"title": "Conclusion", "rows": _kept_rows([
                ("Points forts", item.strengths),
                ("Points de vigilance", item.weaknesses),
                ("Conditions proposées", item.recommended_conditions),
                ("Avis de l'analyste", item.comment),
                ("Commentaire de vérification", item.verification_comment),
                ("Documents consultés", _consulted_documents(application, item)),
            ]) + documents},
        ])
        analyses.append({
            "title": f"Analyse du {_date(item.created_at)}",
            "sections": [block for block in sections if block["rows"]],
            "tables": _comparison_tables(item, currency),
        })
    return analyses


def _guarantees(application, currency: str) -> list[tuple]:
    rows = []
    for item in application.guarantees.all().order_by("created_at"):
        if item.belongs_to_applicant:
            owner = item.client.display_name if item.client_id else "—"
        elif item.surety_id:
            owner = item.surety.display_name
        else:
            owner = item.owners or "—"
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


def _documents(application) -> dict:
    attached_labels = {
        (doc.label or "").strip()
        for doc in application.documents.all()
        if (doc.label or "").strip()
    }
    missing = []
    checklist = application.document_checklist or []
    has_checklist = isinstance(checklist, list) and any(
        isinstance(item, dict) and str(item.get("label") or "").strip() for item in checklist
    )
    if isinstance(checklist, list):
        for item in checklist:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip()
            if not label or label in attached_labels:
                continue
            missing.append((label, "Non jointe"))
    files = []
    if application.request_letter_scan:
        files.append(("Lettre de demande", "Scan", _file_name(application.request_letter_scan)))
    if application.tax_regime != "INFORMAL":
        for field, label in (
            (application.activity_ifu_scan, "IFU"),
            (application.activity_rccm_scan, "RCCM"),
            (application.activity_ninea_scan, "NINEA"),
        ):
            if field:
                files.append((label, "Scan", _file_name(field)))
    for photo in application.stock_photos.all():
        files.append((photo.caption or "Photo", "Photo", _file_name(photo.image)))
    for doc in application.documents.all():
        files.append((doc.label or "Pièce", "Document", _file_name(doc.file)))
    return {"missing": missing, "files": files, "has_checklist": has_checklist}


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
    wash = _tint(brand["primary"], 0.08)
    ink_on_sidebar = _color(brand["sidebar_text"])

    styles = {
        "h1": ParagraphStyle("h1", fontName=font_b, fontSize=16, leading=20, textColor=body),
        "meta": ParagraphStyle("meta", fontName=font, fontSize=8.5, leading=11, textColor=muted),
        "section": ParagraphStyle("section", fontName=font_b, fontSize=11, leading=14, textColor=primary),
        "index": ParagraphStyle("index", fontName=font_b, fontSize=9, leading=12, textColor=accent),
        "sub": ParagraphStyle("sub", fontName=font_b, fontSize=9, leading=12, textColor=secondary),
        "chip_label": ParagraphStyle("chip_label", fontName=font_b, fontSize=7, leading=9, textColor=secondary),
        "chip_value": ParagraphStyle("chip_value", fontName=font_b, fontSize=10, leading=13, textColor=body),
        "body": ParagraphStyle("body", fontName=font, fontSize=9, leading=12, textColor=body, alignment=TA_LEFT),
        "small": ParagraphStyle("small", fontName=font, fontSize=8, leading=10, textColor=body),
        "small_b": ParagraphStyle("small_b", fontName=font_b, fontSize=8, leading=10, textColor=ink_on_sidebar),
        "note": ParagraphStyle("note", fontName=font, fontSize=8, leading=11, textColor=muted),
    }

    def para(text, style="body"):
        safe = escape(_text(text) if text is not None else "—").replace("\n", "<br/>")
        return Paragraph(safe, styles[style])

    page_width = 178 * mm

    def section(index, title):
        band = Table(
            [[
                Paragraph(f"{index:02d}", styles["index"]),
                Paragraph(escape(title), styles["section"]),
            ]],
            colWidths=[14 * mm, page_width - 14 * mm],
        )
        band.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), wash),
            ("LINEBEFORE", (0, 0), (0, 0), 3.5, accent),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (0, 0), 8),
            ("LEFTPADDING", (1, 0), (1, 0), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        return band

    def kv(pairs):
        if not pairs:
            return para("Aucune information enregistrée.", "note")
        rows = [[para(label, "small"), para(value, "small")] for label, value in pairs]
        table = Table(rows, colWidths=[64 * mm, page_width - 64 * mm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), wash),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, -1), 0.3, line),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        return table

    def grid(headers, rows, widths):
        if not rows:
            return para("Aucune information enregistrée.", "note")
        head = [Paragraph(escape(item), styles["small_b"]) for item in headers]
        body_rows = [[para(cell, "small") for cell in row] for row in rows]
        table = Table([head, *body_rows], colWidths=widths, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), sidebar),
            ("TEXTCOLOR", (0, 0), (-1, 0), ink_on_sidebar),
            ("LINEBELOW", (0, 0), (-1, 0), 2, accent),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 1), (-1, -1), 0.25, line),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, wash]),
        ]))
        return table

    def subtitle(title):
        return Paragraph(escape(title), styles["sub"])

    def missing_note():
        return para("Aucune information enregistrée.", "note")

    story = []
    chips = []
    for label, value in (
        ("Client", data["client_name"]),
        ("Référence", data["reference"]),
        ("Montant", data["headline_amount"]),
        ("Statut", data["status"]),
    ):
        chips.append([
            Paragraph(escape(label.upper()), styles["chip_label"]),
            Paragraph(escape(str(value)), styles["chip_value"]),
        ])
    hero = Table([chips], colWidths=[page_width / 4] * 4)
    hero.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), wash),
        ("LINEABOVE", (0, 0), (-1, 0), 3, accent),
        ("LINEBEFORE", (1, 0), (-1, -1), 0.4, line),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(hero)
    story.append(Spacer(1, 5))
    story.append(Paragraph(
        escape(f"{data['product_label']}   ·   {data['agency_label']}   ·   Généré le {data['generated_at']}"),
        styles["meta"],
    ))
    story.append(Spacer(1, 8))

    blocks = []
    profile = data["profile_blocks"]
    documents = data["documents"]

    def add(title, flowable):
        blocks.append((title, flowable))

    add("Profil client", kv(data["client_rows"]) if data["client_rows"] else missing_note())
    if profile["compliance"]:
        add("Conformité (LBC-FT)", kv(profile["compliance"]))
    if data["is_individual"] or profile["applicant"]:
        add("Profil du demandeur", kv(profile["applicant"]) if profile["applicant"] else missing_note())

    terms = [kv(data["terms"]) if data["terms"] else missing_note()]
    if data["fees"]:
        terms.extend([
            Spacer(1, 5), subtitle("Frais"), Spacer(1, 2),
            grid(["Intitulé", "Valeur"], data["fees"], [112 * mm, 66 * mm]),
        ])
    if data["loan_rows"]:
        terms.extend([Spacer(1, 5), subtitle("Mise en place"), Spacer(1, 2), kv(data["loan_rows"])])
    if any(value != "—" for _, value in data["cbs_rows"]):
        terms.extend([Spacer(1, 5), subtitle("Références CBS"), Spacer(1, 2), kv(data["cbs_rows"])])
    add("Caractéristiques du prêt", terms)

    collateral = []
    if profile["premises"]:
        collateral.extend([kv([("Occupation des locaux", profile["premises"])]), Spacer(1, 5)])
    collateral.extend([
        subtitle("Garanties"), Spacer(1, 2),
        grid(
            ["Référence", "Type", "Statut", "Valeur", "Propriétaire", "Description"],
            data["guarantees"],
            [22 * mm, 36 * mm, 22 * mm, 28 * mm, 30 * mm, 40 * mm],
        ),
        Spacer(1, 5), subtitle("Cautions"), Spacer(1, 2),
        grid(
            ["Caution", "Montant engagé", "Statut"],
            data["sureties"],
            [84 * mm, 52 * mm, 42 * mm],
        ),
    ])
    add("Garanties et cautions", collateral)

    if profile["special"]:
        add("Conditions particulières", kv(profile["special"]))
    add(
        "Plan de financement",
        kv(profile["financing"]) if profile["financing"] else para(
            "Coût du projet, apport et quotité financée non renseignés.", "note",
        ),
    )
    schedule = data["schedule"]
    if schedule.get("rows"):
        schedule_parts = []
        if schedule.get("note"):
            schedule_parts.extend([para(schedule["note"], "note"), Spacer(1, 4)])
        schedule_parts.append(grid(
            ["N°", "Échéance", "Capital", "Intérêts", "Total", schedule.get("last") or "Reste dû"],
            schedule["rows"],
            [14 * mm, 28 * mm, 32 * mm, 32 * mm, 36 * mm, 36 * mm],
        ))
        add("Échéancier", schedule_parts)
    if profile["banking"]:
        add("Comptes hors institution", kv(profile["banking"]))
    if data["exposure"] is not None:
        exposure = data["exposure"]
        exposure_parts = []
        if exposure.get("client_total") is not None or exposure.get("group_total") is not None:
            exposure_parts.extend([kv([
                ("Total client", _money(exposure.get("client_total"), exposure.get("currency"))),
                ("Total du groupe lié", _money(exposure.get("group_total"), exposure.get("currency"))),
            ]), Spacer(1, 4)])
        exposure_parts.append(grid(
            ["Personne", "Externe", "En circuit", "Total", "Points d'attention"],
            exposure.get("rows") or [],
            [42 * mm, 28 * mm, 28 * mm, 28 * mm, 52 * mm],
        ))
        if exposure.get("failures"):
            exposure_parts.extend([Spacer(1, 4), para(" ; ".join(exposure["failures"]), "note")])
        if exposure.get("note"):
            exposure_parts.append(para(exposure["note"], "note"))
        add("Engagements", exposure_parts)
    if profile["activity"]:
        add("Activité", kv(profile["activity"]))
    add("Visites terrain", grid(
        ["Date", "Auteur", "Lieu visité", "Personne", "Conclusion", "Compte rendu"],
        data["visits"],
        [22 * mm, 30 * mm, 32 * mm, 26 * mm, 26 * mm, 42 * mm],
    ))
    if data["analyses"]:
        parts = []
        for analysis in data["analyses"]:
            parts.extend([subtitle(analysis["title"]), Spacer(1, 3)])
            for block in analysis.get("sections") or []:
                parts.extend([subtitle(block["title"]), Spacer(1, 2), kv(block["rows"]), Spacer(1, 4)])
            for table in analysis.get("tables") or []:
                parts.extend([
                    Spacer(1, 4), subtitle(table["title"]), Spacer(1, 2),
                    grid(
                        table["headers"], table["rows"],
                        [width * 178 / sum(table["widths"]) * mm for width in table["widths"]],
                    ),
                ])
            parts.append(Spacer(1, 6))
        add("Analyse financière", parts)
    else:
        add("Analyse financière", para("Aucune analyse enregistrée.", "note"))
    if documents["has_checklist"]:
        if documents["missing"]:
            add("Pièces à réunir", grid(
                ["Libellé", "État"], documents["missing"], [120 * mm, 58 * mm],
            ))
        else:
            add("Pièces à réunir", para("Toutes les pièces listées sont déjà jointes.", "note"))
    add("Fichiers déjà joints", grid(
        ["Libellé", "Nature", "Fichier"], documents["files"], [74 * mm, 34 * mm, 70 * mm],
    ))
    if data["contracts"]:
        add("Contrats", grid(
            ["Contrat", "Statut", "Généré le", "Par", "Signé le"],
            data["contracts"],
            [52 * mm, 28 * mm, 32 * mm, 34 * mm, 32 * mm],
        ))
    if data["conditions"]:
        add("Réserves", grid(
            ["Statut", "Réserve", "Émise par"],
            data["conditions"],
            [36 * mm, 100 * mm, 42 * mm],
        ))
    add("Historique et audit", grid(
        ["Date", "Événement", "Acteur", "Détail"],
        data["history"],
        [34 * mm, 38 * mm, 42 * mm, 64 * mm],
    ))
    add("Circuit d'approbation", grid(
        ["Étape", "Décision", "Avis", "Acteur", "Date", "Commentaire"],
        data["decisions"],
        [34 * mm, 24 * mm, 26 * mm, 30 * mm, 28 * mm, 36 * mm],
    ))

    for index, (title, flowable) in enumerate(blocks, start=1):
        story.append(KeepTogether([section(index, title), Spacer(1, 3)]))
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
        topMargin=28 * mm,
        bottomMargin=18 * mm,
        title=f"Dossier {data['reference']}",
        author=data["filiale"],
    )
    logo_bytes = data.get("logo")

    def paint(canvas, doc_):
        canvas.saveState()
        width, height = A4
        header_h = 18 * mm
        canvas.setFillColor(sidebar)
        canvas.rect(0, height - header_h, width, header_h, fill=1, stroke=0)
        canvas.setFillColor(accent)
        canvas.rect(0, height - header_h - 1.8 * mm, width, 1.8 * mm, fill=1, stroke=0)
        text_x = 14 * mm
        if logo_bytes:
            try:
                from reportlab.lib.utils import ImageReader

                canvas.setFillColor(white)
                canvas.roundRect(8 * mm, height - header_h + 2.4 * mm, 18 * mm, 13.2 * mm, 1.6 * mm, fill=1, stroke=0)
                canvas.drawImage(
                    ImageReader(io.BytesIO(logo_bytes)),
                    9 * mm,
                    height - header_h + 3 * mm,
                    width=16 * mm,
                    height=12 * mm,
                    preserveAspectRatio=True,
                    mask="auto",
                    anchor="c",
                )
                text_x = 30 * mm
            except Exception:
                text_x = 14 * mm
        canvas.setFillColor(sidebar_text)
        canvas.setFont(font_b, 12)
        canvas.drawString(text_x, height - 8 * mm, data["filiale"][:58])
        canvas.setFont(font, 8)
        canvas.drawRightString(width - 12 * mm, height - 7.6 * mm, "Dossier de crédit")
        if data.get("filiale_meta"):
            canvas.setFont(font, 7.5)
            canvas.drawString(text_x, height - 13.2 * mm, data["filiale_meta"][:95])
        canvas.setFillColor(accent)
        canvas.rect(0, 12 * mm, width, 1.4 * mm, fill=1, stroke=0)
        canvas.setFillColor(sidebar)
        canvas.rect(0, 0, width, 12 * mm, fill=1, stroke=0)
        canvas.setFillColor(sidebar_text)
        canvas.setFont(font, 8)
        canvas.drawString(12 * mm, 4.4 * mm, f"{data['filiale']}   ·   {data['reference']}"[:80])
        canvas.drawRightString(width - 12 * mm, 4.4 * mm, f"Page {doc_.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=paint, onLaterPages=paint)
    return buffer.getvalue()
