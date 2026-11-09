"""Données structurées de reconstitution, communes à la banque et au SFD.

Les tableaux complètent les agrégats ; les écarts sont signalés et restent
explicitement à rapprocher par l'analyste, sans écrasement de sa saisie.
"""
import re
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from rest_framework.exceptions import ValidationError


DETAIL_SCHEMAS = {
    "products": {
        "name": "text", "unit": "text", "nature": "text", "quantity": "amount",
        "quantity_produced": "amount", "quantity_scrapped": "amount",
        "sale_price": "amount", "unit_cost": "amount",
        "material_cost": "amount", "direct_labor": "amount",
        "other_production_cost": "amount", "comment": "text",
    },
    "stocks": {
        "name": "text", "quantity": "amount", "unit_cost": "amount",
        "impaired_value": "amount", "count_date": "date", "comment": "text",
    },
    "debts": {
        "lender": "text", "kind": "text", "outstanding": "amount",
        "monthly_payment": "amount", "arrears": "amount", "maturity": "date",
        "disbursement_date": "date", "status": "text", "behavior": "text",
        "comment": "text",
    },
    "external_credits": {
        "institution": "text", "grant_date": "date", "final_due_date": "date",
        "initial_amount": "amount", "monthly_payment": "amount",
        "outstanding": "amount", "max_days_late": "amount",
        "bureau_checked": "text", "bureau_date": "date",
        "incidents": "text", "incidents_detail": "text",
    },
    "sales_observations": {
        "kind": "text", "label": "text", "amount": "amount",
    },
    "bank_flows": {
        "institution": "text", "period": "text", "tmc": "amount",
        "balance": "signed", "average_tmc": "amount",
    },
    "references": {
        "kind": "text", "name": "text", "relationship": "text",
        "phone": "text", "address": "text",
    },
    "cashflow": {
        "month": "month", "inflows": "amount", "outflows": "amount",
        "existing_service": "amount", "new_service": "amount",
        "investment": "amount", "comment": "text",
    },
    "history": {
        "period": "text", "turnover": "amount", "net_result": "signed",
        "cashflow": "signed", "equity": "signed", "comment": "text",
    },
}
DETAIL_TEXTS = {
    "business_model", "seasonality", "sales_verification", "stock_risks",
    "receivables_quality", "asset_ownership", "household_income_evidence",
    "employment_outlook", "project_cost", "own_contribution",
    "financing_plan", "stress_assumptions", "monitoring_plan",
    "bureau_reference", "bureau_discrepancies", "banking_behavior",
    "cash_check_comment",
    "production_main_products", "production_process", "production_capacity",
    "production_utilization", "production_main_material", "production_other_inputs",
    "production_workshop", "production_workforce",     "production_quality",
    "production_comment", "group_activity_description",
    "campaign_name", "campaign_production", "campaign_scale", "campaign_inflow_months",
    "campaign_calendar", "campaign_sales", "campaign_comment",
    "creation_activity", "creation_ramp", "creation_assumptions",
    "minimal_cash_label", "minimal_cash_comment",
}

DETAIL_CHOICES = {
    "sales_method": {"", "CAHIER", "BANK", "THREE_DAYS", "STOCK", "HYPOTHESIS", "OTHER"},
    "purchase_method": {"", "INVOICES", "LEDGER", "COST_RATE", "OTHER"},
    "statement_basis": {"", "STATEMENTS", "RECONSTITUTED"},
    "manufactures": {"", "yes", "no"},
    "group_has_activity": {"", "yes", "no"},
    "campaign_open": {"", "yes", "no"},
    "activity_creation": {"", "yes", "no"},
    "minimal_cash_open": {"", "yes", "no"},
}

DETAIL_DATES = {"last_purchase_date", "cash_control_date", "minimal_cash_start", "minimal_cash_end"}

SALES_OBSERVATION_KINDS = {"", "Observé", "Hypothèse"}
REFERENCE_KINDS = {"", "Familiale", "Professionnelle"}

# Compléments facultatifs : l'absence reste distincte d'un zéro renseigné.
DETAIL_AMOUNTS = {
    "opening_cash_balance": "signed", "declared_equity": "signed",
    "bfr_change": "signed", "maintenance_investment": "amount",
    "income_tax_expense": "amount", "provision_expense": "amount",
    "provision_reversal": "amount", "exceptional_income": "amount",
    "exceptional_expense": "amount", "fixed_operating_costs": "amount",
    "variable_operating_costs": "amount", "period_purchases": "amount",
    "opening_stock": "amount", "opening_receivables": "amount",
    "opening_supplier_debt": "amount", "purchase_stress_pct": "percent",
    "receivable_delay_days": "amount",
    "activity_days_per_month": "amount", "retained_daily_sales": "amount",
    "sales_control_monthly": "amount",
    "purchase_average": "amount", "purchase_frequency": "amount",
    "safety_provision_pct": "percent", "last_purchase_amount": "amount",
    "cash_at_last_purchase": "signed", "charges_paid_in_window": "amount",
    "other_outflows_in_window": "amount", "observed_cash": "signed",
    "cash_tolerance_pct": "percent",
    "production_stock_materials": "amount",
    "production_stock_wip": "amount",
    "production_stock_finished": "amount",
    "campaign_revenue": "amount",
    "campaign_charges": "amount",
    "campaign_input_stock": "amount",
    "campaign_harvest_stock": "amount",
    "minimal_cash_opening": "signed",
    "minimal_cash_inflows": "amount",
    "minimal_cash_outflows": "amount",
    "minimal_cash_closing": "signed",
}

PRODUCT_NATURES = {"", "RESOLD", "MANUFACTURED", "SERVICE"}
PRODUCTION_COST_KEYS = ("material_cost", "direct_labor", "other_production_cost")

MONEY = Decimal("0.01")


def detail_amount(analysis, key, default=Decimal("0")):
    value = (analysis.analysis_details or {}).get(key)
    return default if value in (None, "") else Decimal(str(value))


def validate_details(value):
    if not isinstance(value, dict):
        raise ValidationError("Le détail de l'analyse doit être un objet.")
    unknown = (
        set(value) - set(DETAIL_SCHEMAS) - DETAIL_TEXTS - set(DETAIL_AMOUNTS)
        - set(DETAIL_CHOICES) - DETAIL_DATES
        - {"cash_detail_mode", "fixed_assets_detail_mode", "financial_statements", "minimal_cash_document"}
    )
    if unknown:
        raise ValidationError(f"Rubriques inconnues : {', '.join(sorted(unknown))}.")
    for key, text in value.items():
        if key == "financial_statements":
            _validate_financial_statements(text)
            continue
        if key == "minimal_cash_document":
            if text in (None, ""):
                continue
            if not isinstance(text, str) or not _STATEMENT_UUID.match(text):
                raise ValidationError({key: "Document invalide."})
            continue
        if key in {"cash_detail_mode", "fixed_assets_detail_mode"}:
            if text not in ("", "DETAIL", "LEGACY"):
                raise ValidationError({key: "Choisissez DETAIL ou LEGACY."})
            continue
        if key in DETAIL_AMOUNTS:
            if text in (None, ""):
                continue
            try:
                number = Decimal(str(text))
                valid = number.is_finite() and abs(number) < Decimal("1e16")
                valid = valid and (DETAIL_AMOUNTS[key] == "signed" or number >= 0)
                valid = valid and (DETAIL_AMOUNTS[key] != "percent" or number <= 100)
            except (InvalidOperation, TypeError, ValueError):
                valid = False
            if not valid:
                raise ValidationError({key: "Montant invalide."})
            continue
        if key in DETAIL_CHOICES:
            if text not in DETAIL_CHOICES[key]:
                raise ValidationError({key: "Méthode inconnue."})
            continue
        if key in DETAIL_DATES:
            if text in (None, ""):
                continue
            try:
                date.fromisoformat(str(text))
            except ValueError:
                raise ValidationError({key: "Date attendue, au format AAAA-MM-JJ."}) from None
            continue
        if key in DETAIL_TEXTS:
            if not isinstance(text, str) or len(text) > 10000:
                raise ValidationError({key: "Texte attendu, limité à 10 000 caractères."})
            if key == "minimal_cash_label" and len(text) > 150:
                raise ValidationError({key: "L'intitulé de la période est limité à 150 caractères."})
            continue
        rows = text
        if not isinstance(rows, list) or len(rows) > 120:
            raise ValidationError({key: "Tableau attendu, limité à 120 lignes."})
        months = set()
        for index, row in enumerate(rows):
            if not isinstance(row, dict) or set(row) - set(DETAIL_SCHEMAS[key]):
                raise ValidationError({key: f"Ligne {index + 1} : colonnes invalides."})
            for field, content in row.items():
                if content in ("", None):
                    continue
                kind = DETAIL_SCHEMAS[key][field]
                valid = True
                if kind in ("amount", "signed"):
                    try:
                        number = Decimal(str(content))
                        valid = number.is_finite() and abs(number) < Decimal("1e16")
                        valid = valid and (kind == "signed" or number >= 0)
                    except (InvalidOperation, ValueError):
                        valid = False
                elif kind in ("date", "month"):
                    try:
                        date.fromisoformat(str(content) + ("-01" if kind == "month" else ""))
                        if kind == "month":
                            valid = str(content) not in months
                            months.add(str(content))
                    except ValueError:
                        valid = False
                else:
                    valid = isinstance(content, str) and len(content) <= 1000
                if not valid:
                    raise ValidationError({key: f"Ligne {index + 1}, {field} : valeur invalide."})
            if key == "products":
                nature = str(row.get("nature") or "")
                if nature not in PRODUCT_NATURES:
                    raise ValidationError({key: f"Ligne {index + 1} : indiquez Revendu, Fabriqué ou Service."})
            if key == "stocks":
                total = Decimal(str(row.get("quantity") or 0)) * Decimal(str(row.get("unit_cost") or 0))
                if Decimal(str(row.get("impaired_value") or 0)) > total:
                    raise ValidationError({key: f"Ligne {index + 1} : dépréciation supérieure au stock brut."})
            if key == "sales_observations" and str(row.get("kind") or "") not in SALES_OBSERVATION_KINDS:
                raise ValidationError({key: f"Ligne {index + 1} : indiquez Observé ou Hypothèse."})
            if key == "references" and str(row.get("kind") or "") not in REFERENCE_KINDS:
                raise ValidationError({key: f"Ligne {index + 1} : indiquez Familiale ou Professionnelle."})
            if key == "external_credits":
                checked = str(row.get("bureau_checked") or "")
                incidents = str(row.get("incidents") or "")
                if checked not in {"", "yes", "no"} or incidents not in {"", "yes", "no"}:
                    raise ValidationError({key: f"Ligne {index + 1} : répondez par oui ou non."})
                if checked == "yes" and not row.get("bureau_date"):
                    raise ValidationError({key: f"Ligne {index + 1} : indiquez la date de consultation."})
                grant = str(row.get("grant_date") or "")
                final = str(row.get("final_due_date") or "")
                if grant and final and final < grant:
                    raise ValidationError({key: f"Ligne {index + 1} : la dernière échéance est antérieure à la date d'octroi."})
                delay = row.get("max_days_late")
                if delay not in (None, ""):
                    try:
                        days = Decimal(str(delay))
                        if days < 0 or days != days.to_integral_value():
                            raise InvalidOperation
                    except (InvalidOperation, ValueError):
                        raise ValidationError({key: f"Ligne {index + 1} : le retard se saisit en jours entiers."}) from None
    _validate_tpe_bounds(value)
    start = str(value.get("minimal_cash_start") or "")
    end = str(value.get("minimal_cash_end") or "")
    if start and end and end < start:
        raise ValidationError({"minimal_cash_end": "La date de fin est antérieure à la date de début."})
    return value


def _validate_tpe_bounds(value):
    days = value.get("activity_days_per_month")
    if days not in (None, "") and not (Decimal("0") < Decimal(str(days)) <= Decimal("31")):
        raise ValidationError({"activity_days_per_month": "Indiquez entre 1 et 31 jours d'activité par mois."})
    frequency = value.get("purchase_frequency")
    if frequency not in (None, "") and not (Decimal("0") < Decimal(str(frequency)) <= Decimal("100")):
        raise ValidationError({"purchase_frequency": "Indiquez entre 1 et 100 approvisionnements par mois."})
    start = value.get("last_purchase_date") or ""
    end = value.get("cash_control_date") or ""
    if start and end and end < start:
        raise ValidationError({"cash_control_date": "La date du contrôle est antérieure au dernier achat."})


def product_nature(row):
    nature = str(row.get("nature") or "")
    return nature if nature in {"MANUFACTURED", "SERVICE"} else "RESOLD"


def _present_decimal(row, key):
    value = row.get(key)
    if value in (None, ""):
        return None
    return Decimal(str(value))


def product_line_figures(row):
    """Chiffre d'affaires retenu, coût des unités vendues et marge.

    Une case vide reste vide. Le service sans coût direct a un coût nul :
    le champ n'est pas réécrit. Le fabriqué retient la quantité vendue,
    et son coût unitaire sort des coûts de production divisés par la
    quantité produite.
    """
    sold = _present_decimal(row, "quantity")
    price = _present_decimal(row, "sale_price")
    sales = None if sold is None or price is None else sold * price
    nature = product_nature(row)
    if nature == "MANUFACTURED":
        produced = _present_decimal(row, "quantity_produced")
        parts = [_present_decimal(row, key) for key in PRODUCTION_COST_KEYS]
        if produced is None or produced <= 0 or any(part is None for part in parts):
            unit = None
        else:
            unit = sum(parts, Decimal("0")) / produced
        cost = None if unit is None or sold is None else unit * sold
    elif nature == "SERVICE":
        unit = _present_decimal(row, "unit_cost")
        cost = None if sold is None else (Decimal("0") if unit is None else unit * sold)
    else:
        unit = _present_decimal(row, "unit_cost")
        cost = None if unit is None or sold is None else unit * sold
    margin = None if sales is None or cost is None else sales - cost
    return {"sales": sales, "cost": cost, "unit_cost": unit, "margin": margin}


def detail_metrics(analysis):
    details = analysis.analysis_details or {}

    def number(row, key):
        return Decimal(str(row.get(key) or 0))

    metrics = {}
    if details.get("products"):
        figures = [product_line_figures(row) for row in details["products"]]
        sales_complete = all(item["sales"] is not None for item in figures)
        costs_complete = all(item["cost"] is not None for item in figures)
        metrics["product_details_complete"] = sales_complete and costs_complete
        metrics["reconstituted_sales"] = sum((item["sales"] for item in figures), Decimal("0")) if sales_complete else None
        metrics["reconstituted_cost"] = sum((item["cost"] for item in figures), Decimal("0")) if costs_complete else None
        metrics["reconstituted_margin"] = metrics["reconstituted_sales"] - metrics["reconstituted_cost"] if sales_complete and costs_complete else None
        declared = analysis.turnover if analysis.is_corporate else analysis.activity_turnover if analysis.is_individual else analysis.group_activity_turnover
        metrics["sales_gap"] = metrics["reconstituted_sales"] - Decimal(str(declared or 0)) if sales_complete else None
        metrics["sales_reconciled"] = abs(metrics["sales_gap"]) <= Decimal("0.01") if sales_complete else None
    if details.get("stocks"):
        complete = all(all(row.get(key) not in (None, "") for key in ("quantity", "unit_cost")) for row in details["stocks"])
        metrics["stock_details_complete"] = complete
        metrics["inventory_net_value"] = sum(
            (number(row, "quantity") * number(row, "unit_cost")
             - number(row, "impaired_value") for row in details["stocks"]),
            Decimal("0"),
        ) if complete else None
        declared = analysis.stock_value if analysis.is_corporate else analysis.activity_stock_value if analysis.is_individual else None
        metrics["stock_gap"] = metrics["inventory_net_value"] - Decimal(str(declared)) if declared is not None and complete else None
        metrics["stock_reconciled"] = abs(metrics["stock_gap"]) <= Decimal("0.01") if metrics["stock_gap"] is not None else None
    if details.get("debts"):
        metrics["debt_details_complete"] = all(all(row.get(key) not in (None, "") for key in ("outstanding", "monthly_payment")) for row in details["debts"])
        for target, column in (
            ("detailed_debt_outstanding", "outstanding"),
            ("detailed_debt_monthly", "monthly_payment"),
            ("detailed_debt_arrears", "arrears"),
        ):
            complete = all(row.get(column) not in (None, "") for row in details["debts"])
            metrics[target] = sum(
                (number(row, column) for row in details["debts"]), Decimal("0")
            ) if complete else None
        metrics["debt_service_reconciled"] = (
            metrics["detailed_debt_monthly"] is not None and abs(metrics["detailed_debt_monthly"] - analysis.existing_debt_monthly) <= Decimal("0.01")
        )
        metrics["outstanding_gap"] = metrics["detailed_debt_outstanding"] - analysis.ongoing_credit_balance if metrics["detailed_debt_outstanding"] is not None else None
        metrics["outstanding_reconciled"] = abs(metrics["outstanding_gap"]) <= Decimal("0.01") if metrics["outstanding_gap"] is not None else None
    if details.get("cashflow"):
        rows = sorted(details["cashflow"], key=lambda row: row.get("month") or "")
        months = [row.get("month") for row in rows]
        complete = all(months) and len(set(months)) == len(months)
        if complete:
            ordinals = [int(month[:4]) * 12 + int(month[5:7]) for month in months]
            complete = all(right - left == 1 for left, right in zip(ordinals, ordinals[1:]))
        balance = detail_amount(analysis, "opening_cash_balance", None) if complete else None
        opening = balance
        forecast, flows, closings = [], [], []
        for row in rows:
            flow = (number(row, "inflows") - number(row, "outflows") - number(row, "investment")
                    - number(row, "existing_service") - number(row, "new_service"))
            start = balance
            balance = balance + flow if balance is not None else None
            forecast.append({"month": row.get("month"), "opening": start, "net_flow": flow, "closing": balance,
                             "existing_service": number(row, "existing_service"), "new_service": number(row, "new_service")})
            flows.append(flow)
            if balance is not None:
                closings.append(balance)
        metrics.update({
            "forecast_rows": forecast, "forecast_complete": bool(complete),
            "forecast_opening_balance": opening, "forecast_lowest_flow": min(flows),
            "forecast_lowest_balance": min(closings) if closings else None,
            "forecast_closing_balance": balance,
            "forecast_negative_flow_months": sum(flow < 0 for flow in flows),
            "forecast_cash_deficit_months": sum(item < 0 for item in closings) if closings else None,
            # Compatibilité du contrôle de soumission : préférer la trésorerie
            # cumulée lorsqu'elle est connue, sinon conserver l'alerte sur flux.
            "forecast_deficit_months": sum(item < 0 for item in closings) if closings else sum(flow < 0 for flow in flows),
        })
    metrics.update(_tpe_metrics(analysis, details, metrics))
    reading = minimal_cash_reading(details)
    if reading:
        metrics.update(reading)
    return metrics


def _money(value):
    if value is None:
        return None
    return Decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)


def _optional(details, key):
    value = details.get(key)
    if value in (None, ""):
        return None
    return Decimal(str(value))


def minimal_cash_reading(details):
    """Lecture du document court. Elle ne modifie aucun ratio.

    Une case vide reste vide. Dès qu'une ligne du mouvement est saisie,
    l'autre compte pour zéro. Le surplus est entrées moins sorties.
    """
    if not isinstance(details, dict) or details.get("minimal_cash_open") != "yes":
        return {}
    opening = _optional(details, "minimal_cash_opening")
    inflows = _optional(details, "minimal_cash_inflows")
    outflows = _optional(details, "minimal_cash_outflows")
    closing = _optional(details, "minimal_cash_closing")
    result = {}
    if inflows is not None or outflows is not None:
        result["minimal_cash_surplus"] = _money((inflows or Decimal("0")) - (outflows or Decimal("0")))
    if any(item is not None for item in (opening, inflows, outflows)):
        theoretical = _money((opening or Decimal("0")) + (inflows or Decimal("0")) - (outflows or Decimal("0")))
        result["minimal_cash_theoretical_closing"] = theoretical
        if closing is not None:
            result["minimal_cash_gap"] = _money(closing - theoretical)
    return result


def campaign_capacity(analysis):
    """Surplus de campagne réparti sur la durée du crédit.

    Les deux montants vides restent vides. Un seul montant saisi compte
    l'autre comme zéro. Les stocks d'intrants et de récolte ne sont pas
    des recettes. None si la case est fermée ou si la durée manque.
    """
    if not getattr(analysis, "uses_campaign", False):
        return None
    details = analysis.analysis_details or {}
    revenue = _optional(details, "campaign_revenue")
    charges = _optional(details, "campaign_charges")
    if revenue is None and charges is None:
        return None
    surplus = (revenue or Decimal("0")) - (charges or Decimal("0"))
    app = getattr(analysis, "application", None)
    months = getattr(app, "duration_months", None) if app is not None else None
    if not months:
        return None
    return {
        "campaign_surplus": _money(surplus),
        "campaign_monthly_surplus": _money(surplus / Decimal(months)),
        "campaign_duration_months": int(months),
    }


def _monthly(analysis, amount):
    if amount is None:
        return None
    return _money(Decimal(str(amount)) * analysis.reference_periods_per_year / Decimal("12"))


def _filled_rows(rows):
    return [row for row in rows if any(value not in (None, "") for value in row.values())]


def _average(rows, kind):
    selected = [row for row in _filled_rows(rows) if (row.get("kind") or "Observé") == kind]
    if not selected or any(row.get("amount") in (None, "") for row in selected):
        return None
    total = sum((Decimal(str(row["amount"])) for row in selected), Decimal("0"))
    return _money(total / Decimal(len(selected)))


def _relative(gap, base):
    if gap is None or base in (None, 0):
        return None
    return _money(gap / Decimal(base) * Decimal("100"))


def _tpe_metrics(analysis, details, current):
    result = {}
    observed = _average(details.get("sales_observations") or [], "Observé")
    hypothesis = _average(details.get("sales_observations") or [], "Hypothèse")
    result["tpe_observed_daily_average"] = observed
    result["tpe_hypothesis_daily_average"] = hypothesis
    method = details.get("sales_method") or ""
    computed = observed if method == "THREE_DAYS" else hypothesis if method == "HYPOTHESIS" else None
    retained = _optional(details, "retained_daily_sales")
    if retained is None:
        retained = computed
    days = _optional(details, "activity_days_per_month")
    monthly = _money(retained * days) if retained is not None and days is not None else None
    result["tpe_retained_daily_sales"] = retained
    result["tpe_monthly_sales"] = monthly
    result["tpe_sales_incomplete"] = method in {"THREE_DAYS", "HYPOTHESIS"} and monthly is None
    declared = None
    if analysis.is_corporate and _dec_positive(analysis.turnover):
        declared = analysis.turnover
    elif analysis.is_individual and _dec_positive(analysis.activity_turnover):
        declared = analysis.activity_turnover
    declared_monthly = _monthly(analysis, declared)
    result["tpe_declared_monthly_sales"] = declared_monthly
    if monthly is not None and declared_monthly is not None:
        gap = _money(monthly - declared_monthly)
        result["tpe_sales_gap"] = gap
        result["tpe_sales_gap_pct"] = _relative(gap, declared_monthly)
        result["tpe_sales_aligned"] = abs(gap) <= max(MONEY, abs(declared_monthly) * Decimal("0.10"))
    control = _optional(details, "sales_control_monthly")
    if monthly is not None and control is not None:
        result["tpe_sales_control_gap"] = _money(monthly - control)
        result["tpe_sales_control_aligned"] = abs(monthly - control) <= max(MONEY, abs(control) * Decimal("0.10"))

    margin_rate = None
    sales = current.get("reconstituted_sales")
    margin = current.get("reconstituted_margin")
    if sales not in (None, 0) and margin is not None:
        margin_rate = Decimal(margin) / Decimal(sales)
    result["tpe_margin_rate_pct"] = _money(margin_rate * Decimal("100")) if margin_rate is not None else None
    purchase_method = details.get("purchase_method") or ""
    purchases = None
    if purchase_method in {"INVOICES", "LEDGER"}:
        average = _optional(details, "purchase_average")
        frequency = _optional(details, "purchase_frequency")
        purchases = _money(average * frequency) if average is not None and frequency is not None else None
        result["tpe_purchases_incomplete"] = purchases is None
    elif purchase_method == "COST_RATE":
        purchases = _money(monthly * (Decimal("1") - margin_rate)) if monthly is not None and margin_rate is not None else None
        result["tpe_purchases_incomplete"] = purchases is None
        result["tpe_cost_rate_pct"] = _money((Decimal("1") - margin_rate) * Decimal("100")) if margin_rate is not None else None
    result["tpe_monthly_purchases"] = purchases
    declared_purchases = None
    if analysis.is_corporate and _dec_positive(analysis.cogs):
        declared_purchases = _monthly(analysis, analysis.cogs)
    elif analysis.is_individual and _dec_positive(analysis.activity_purchases):
        declared_purchases = _monthly(analysis, analysis.activity_purchases)
    result["tpe_declared_monthly_purchases"] = declared_purchases
    if purchases is not None and declared_purchases is not None:
        gap = _money(purchases - declared_purchases)
        result["tpe_purchases_gap"] = gap
        result["tpe_purchases_aligned"] = abs(gap) <= max(MONEY, abs(declared_purchases) * Decimal("0.10"))

    flows = _filled_rows(details.get("bank_flows") or [])
    if flows:
        for source, target in (("tmc", "tpe_tmc_total"), ("balance", "tpe_bank_balance_total")):
            if all(row.get(source) not in (None, "") for row in flows):
                result[target] = _money(sum((Decimal(str(row[source])) for row in flows), Decimal("0")))
        averages = [Decimal(str(row["average_tmc"])) for row in flows if row.get("average_tmc") not in (None, "")]
        if len(averages) == len(flows):
            result["tpe_average_tmc"] = _money(sum(averages, Decimal("0")) / Decimal(len(averages)))

    result.update(_cash_check(analysis, details, retained))
    return result


def _dec_positive(value):
    return value not in (None, "") and Decimal(str(value)) > 0


def _cash_charges(analysis):
    if analysis.is_corporate:
        return analysis.total_operating_expenses * analysis.reference_periods_per_year / Decimal("12")
    if not analysis.is_individual:
        return None
    activity = max(Decimal("0"), _model_dec(analysis, "activity_expenses") - _model_dec(analysis, "activity_purchases"))
    return analysis.monthly_household_charges + activity * analysis.reference_periods_per_year / Decimal("12")


def _model_dec(analysis, name):
    value = getattr(analysis, name, None)
    return Decimal("0") if value in (None, "") else Decimal(str(value))


def _cash_check(analysis, details, retained_daily):
    start = details.get("last_purchase_date") or ""
    end = details.get("cash_control_date") or ""
    opening = _optional(details, "cash_at_last_purchase")
    observed = _optional(details, "observed_cash")
    if not (start and end and opening is not None and observed is not None):
        return {}
    days = (date.fromisoformat(end) - date.fromisoformat(start)).days
    collected = _money(retained_daily * Decimal(days)) if retained_daily is not None else None
    paid = _optional(details, "charges_paid_in_window")
    basis = "OBSERVED" if paid is not None else None
    charges = paid
    warning = False
    if charges is None:
        monthly = _cash_charges(analysis)
        if monthly is not None and monthly > 0:
            charges = _money(monthly * Decimal(days) / Decimal("30"))
            basis = "PRORATA"
            warning = True
    if collected is None or charges is None:
        return {
            "tpe_cash_days": days,
            "tpe_cash_collected": collected,
            "tpe_cash_charges": charges,
            "tpe_cash_incomplete": True,
        }
    other = _optional(details, "other_outflows_in_window") or Decimal("0")
    theoretical = _money(opening + collected - charges - other)
    gap = _money(observed - theoretical)
    tolerance = _optional(details, "cash_tolerance_pct")
    if tolerance is None:
        tolerance = Decimal("10")
    if theoretical == 0:
        gap_pct = Decimal("0") if gap == 0 else None
        conclusion = "COHERENT" if gap == 0 else "TO_JUSTIFY"
    else:
        gap_pct = _relative(gap, theoretical)
        spread = abs(gap_pct)
        conclusion = "COHERENT" if spread <= tolerance else "TO_JUSTIFY" if spread <= tolerance * 2 else "INCOHERENT"
    return {
        "tpe_cash_days": days,
        "tpe_cash_collected": collected,
        "tpe_cash_charges": charges,
        "tpe_cash_charges_basis": basis,
        "tpe_cash_prorata_warning": warning,
        "tpe_cash_other_outflows": _money(other),
        "tpe_cash_theoretical": theoretical,
        "tpe_cash_observed": _money(observed),
        "tpe_cash_gap": gap,
        "tpe_cash_gap_pct": gap_pct,
        "tpe_cash_tolerance_pct": tolerance,
        "tpe_cash_conclusion": conclusion,
        "tpe_cash_long_window": days > 31,
        "tpe_cash_incomplete": False,
    }


def apply_tpe_safety(metrics, analysis):
    """Retenue de prudence sur la capacité déjà nette des dettes existantes.

    Elle ne modifie ni le taux d'endettement ni la décision de capacité :
    les échéances en cours sont déjà déduites de la base.
    """
    pct = _optional(analysis.analysis_details or {}, "safety_provision_pct")
    capacity = metrics.get("repayment_capacity")
    if pct is None or capacity is None:
        return
    capacity = Decimal(str(capacity))
    provision = _money(capacity * pct / Decimal("100"))
    available = _money(capacity - provision)
    installment = metrics.get("installment")
    coverage = None
    if installment is not None and Decimal(str(installment)) > 0:
        coverage = (available / Decimal(str(installment))).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    metrics.update({
        "tpe_safety_pct": pct,
        "tpe_safety_base": _money(capacity),
        "tpe_safety_provision": provision,
        "tpe_safety_available": available,
        "tpe_safety_coverage": coverage,
        "tpe_safety_ok": coverage >= 1 if coverage is not None else None,
    })


_STATEMENT_ID = re.compile(r"^[a-z0-9]{8,64}$")
_STATEMENT_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
STATEMENT_PIECES = ("income", "balance", "cashflow", "notes")
INCOME_KEYS = {
    "sales_goods", "purchases_goods", "variation_goods",
    "sales_manufactured", "sales_services", "accessory_products",
    "stored_production", "capitalized_production", "operating_subsidies",
    "other_operating_products", "operating_charge_transfers",
    "purchases_materials", "variation_materials", "other_purchases", "variation_supplies",
    "transport", "external_services", "taxes", "other_operating_charges", "personnel",
    "operating_reversals", "operating_depreciation",
    "financial_income", "financial_reversals", "financial_charge_transfers",
    "financial_expenses", "financial_depreciation",
    "disposal_proceeds", "other_hao_income", "disposal_book_value", "other_hao_charges",
    "employee_participation", "income_tax", "net_result_read",
}
BALANCE_KEYS = {
    "intangible_development", "intangible_rights", "intangible_goodwill", "intangible_other",
    "intangible_in_progress", "intangible_advances",
    "land", "buildings", "fixtures", "equipment", "transport_equipment", "tangible_advances",
    "investments", "other_financial_assets", "hao_assets",
    "stock_goods", "stock_materials", "stock_wip", "stock_finished",
    "supplier_advances", "customers", "other_receivables",
    "marketable_securities", "instruments_receivable", "cash_and_banks", "translation_asset",
    "capital", "share_premium", "revaluation", "reserves", "retained_earnings", "period_result",
    "investment_grants", "regulated_provisions",
    "borrowings", "lease_debt", "other_financial_debt", "financial_provisions",
    "hao_liabilities", "customer_advances", "suppliers", "tax_social", "other_liabilities",
    "short_provisions", "translation_liability", "discount_credit", "treasury_credit", "bank_overdraft",
}
CASHFLOW_KEYS = {
    "cafg", "operating_bfr_change", "operating_flow", "investing_flow", "financing_flow",
    "cash_change_read", "opening_cash", "closing_cash",
}
NOTE_AMOUNT_KEYS = {
    "fixed_gross", "fixed_depreciation", "fixed_net", "fixed_acquisitions", "fixed_disposals",
    "stock_gross", "stock_impairment", "stock_net",
    "receivable_gross", "receivable_impairment", "receivable_net",
    "debt_current", "debt_noncurrent",
}
NOTE_TEXT_KEYS = {"off_balance", "comment"}
_CHARGE_KEYS = (
    "personnel", "transport", "external_services", "taxes", "other_operating_charges",
    "operating_depreciation", "financial_expenses", "financial_depreciation",
)
_NET_TERMS = (
    ("sales_goods", 1), ("purchases_goods", -1), ("variation_goods", -1),
    ("sales_manufactured", 1), ("sales_services", 1), ("accessory_products", 1),
    ("stored_production", 1), ("capitalized_production", 1), ("operating_subsidies", 1),
    ("other_operating_products", 1), ("operating_charge_transfers", 1),
    ("purchases_materials", -1), ("variation_materials", -1), ("other_purchases", -1),
    ("variation_supplies", -1), ("transport", -1), ("external_services", -1),
    ("taxes", -1), ("other_operating_charges", -1), ("personnel", -1),
    ("operating_reversals", 1), ("operating_depreciation", -1),
    ("financial_income", 1), ("financial_reversals", 1), ("financial_charge_transfers", 1),
    ("financial_expenses", -1), ("financial_depreciation", -1),
    ("disposal_proceeds", 1), ("other_hao_income", 1), ("disposal_book_value", -1),
    ("other_hao_charges", -1), ("employee_participation", -1), ("income_tax", -1),
)


def _statement_amount(value):
    if value in (None, ""):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite() or abs(number) >= Decimal("1e16"):
        return None
    return number


def _present_sum(source, keys):
    if not isinstance(source, dict):
        return None
    total = None
    for key in keys:
        amount = _statement_amount(source.get(key))
        if amount is None:
            continue
        total = amount if total is None else total + amount
    return total


def _signed_sum(source, terms):
    if not isinstance(source, dict):
        return None
    total = None
    for key, sign in terms:
        amount = _statement_amount(source.get(key))
        if amount is None:
            continue
        signed = amount * sign
        total = signed if total is None else total + signed
    return total


def _validate_amount_map(row_label, source, allowed):
    if not isinstance(source, dict) or set(source) - allowed:
        raise ValidationError({row_label: "Rubriques inconnues."})
    for field, content in source.items():
        if content in ("", None):
            continue
        if _statement_amount(content) is None:
            raise ValidationError({row_label: f"{field} : montant invalide."})


def _validate_financial_statements(rows):
    if not isinstance(rows, list) or len(rows) > 20:
        raise ValidationError({"financial_statements": "Indiquez au plus 20 exercices."})
    seen = set()
    allowed = {
        "id", "label", "start_date", "end_date", "nature", "prepared_by", "certified",
        "comment", "income", "balance", "cashflow", "notes", "documents",
    }
    for index, row in enumerate(rows, start=1):
        label = f"financial_statements.{index}"
        if not isinstance(row, dict) or set(row) - allowed:
            raise ValidationError({label: "Colonnes invalides."})
        exercise_id = str(row.get("id") or "")
        if not _STATEMENT_ID.match(exercise_id) or exercise_id in seen:
            raise ValidationError({label: "Identifiant d'exercice invalide ou répété."})
        seen.add(exercise_id)
        title = row.get("label", "")
        comment = row.get("comment", "")
        if not isinstance(title, str) or len(title) > 150 or not isinstance(comment, str) or len(comment) > 10000:
            raise ValidationError({label: "Intitulé ou commentaire invalide."})
        if row.get("nature", "") not in {"", "CLOSED", "INTERIM"}:
            raise ValidationError({label: "Nature d'exercice inconnue."})
        if row.get("prepared_by", "") not in {"", "EXPERT", "FIRM", "CLIENT"}:
            raise ValidationError({label: "Auteur de l'état inconnu."})
        if row.get("certified", "") not in {"", "yes", "no"}:
            raise ValidationError({label: "Indiquez si l'état est visé ou certifié."})
        start, end = str(row.get("start_date") or ""), str(row.get("end_date") or "")
        for raw in (start, end):
            if not raw:
                continue
            try:
                date.fromisoformat(raw)
            except ValueError:
                raise ValidationError({label: "Date attendue, au format AAAA-MM-JJ."}) from None
        if start and end and end < start:
            raise ValidationError({label: "La date de fin est antérieure à la date de début."})
        _validate_amount_map(label, row.get("income", {}), INCOME_KEYS)
        _validate_amount_map(label, row.get("balance", {}), BALANCE_KEYS)
        _validate_amount_map(label, row.get("cashflow", {}), CASHFLOW_KEYS)
        notes = row.get("notes", {})
        if not isinstance(notes, dict) or set(notes) - NOTE_AMOUNT_KEYS - NOTE_TEXT_KEYS - {"headcount"}:
            raise ValidationError({label: "Notes invalides."})
        _validate_amount_map(label, {key: notes.get(key) for key in NOTE_AMOUNT_KEYS if key in notes}, NOTE_AMOUNT_KEYS)
        for text_key in NOTE_TEXT_KEYS:
            text = notes.get(text_key, "")
            if not isinstance(text, str) or len(text) > 10000:
                raise ValidationError({label: "Texte de note invalide."})
        headcount = notes.get("headcount", "")
        if headcount not in ("", None):
            amount = _statement_amount(headcount)
            if amount is None or amount < 0 or amount != amount.to_integral_value():
                raise ValidationError({label: "L'effectif moyen se saisit en nombre entier."})
        documents = row.get("documents", {})
        if not isinstance(documents, dict) or set(documents) - set(STATEMENT_PIECES):
            raise ValidationError({label: "Documents de l'exercice invalides."})
        for piece, document_id in documents.items():
            if document_id in ("", None):
                continue
            if not isinstance(document_id, str) or not _STATEMENT_UUID.match(document_id):
                raise ValidationError({label: f"Document {piece} invalide."})


def _put_amount(attrs, name, amount, *, allow_negative=False):
    if amount is None:
        return
    if not allow_negative and amount < 0:
        amount = Decimal("0")
    attrs[name] = amount


def _put_detail(details, name, amount):
    if amount is None or amount < 0:
        return
    details[name] = format(amount, "f")


def apply_reference_statement(attrs, client_type=None):
    """L'exercice à la date de fin la plus récente alimente les ratios.

    Une ligne vide n'est pas un zéro. Dès qu'un bilan ou un bloc de charges
    est saisi, les postes du moteur qui n'existent pas sur l'état passent à
    zéro pour ne pas conserver une reconstitution antérieure.

    Seule l'entreprise est concernée. Pour une personne physique, les états
    restent une lecture : ils ne remplacent pas le foyer ni l'activité.
    """
    if client_type not in (None, "CORPORATE"):
        return
    details = attrs.get("analysis_details")
    if not isinstance(details, dict) or details.get("statement_basis") != "STATEMENTS":
        return
    rows = details.get("financial_statements")
    if not isinstance(rows, list) or not rows:
        return
    dated = [(index, row) for index, row in enumerate(rows) if isinstance(row, dict) and row.get("end_date")]
    if not dated:
        return
    dated.sort(key=lambda item: (item[1]["end_date"], -item[0]), reverse=True)
    income = dated[0][1].get("income") if isinstance(dated[0][1].get("income"), dict) else {}
    balance = dated[0][1].get("balance") if isinstance(dated[0][1].get("balance"), dict) else {}
    notes = dated[0][1].get("notes") if isinstance(dated[0][1].get("notes"), dict) else {}
    turnover = _present_sum(income, ("sales_goods", "sales_manufactured", "sales_services", "accessory_products"))
    _put_amount(attrs, "turnover", turnover)
    purchases = _present_sum(income, ("purchases_goods", "purchases_materials", "other_purchases"))
    if any(_statement_amount(income.get(key)) is not None for key in _CHARGE_KEYS):
        _put_amount(attrs, "cogs", purchases or Decimal("0"))
        _put_amount(attrs, "op_salaries", _statement_amount(income.get("personnel")) or Decimal("0"))
        _put_amount(attrs, "op_transport", _statement_amount(income.get("transport")) or Decimal("0"))
        _put_amount(attrs, "op_taxes", _statement_amount(income.get("taxes")) or Decimal("0"))
        _put_amount(attrs, "op_other", _present_sum(income, ("external_services", "other_operating_charges")) or Decimal("0"))
        _put_amount(attrs, "depreciation", _statement_amount(income.get("operating_depreciation")) or Decimal("0"))
        _put_amount(attrs, "financial_charges", _present_sum(income, ("financial_expenses", "financial_depreciation")) or Decimal("0"))
        for name in ("op_rent", "op_utilities", "op_telecom", "op_maintenance"):
            attrs[name] = Decimal("0")
    else:
        _put_amount(attrs, "cogs", purchases)
    other_income = _present_sum(income, (
        "stored_production", "capitalized_production", "operating_subsidies",
        "other_operating_products", "operating_charge_transfers",
    ))
    if other_income is not None:
        _put_amount(attrs, "other_operating_income", other_income)
    _put_detail(details, "income_tax_expense", _statement_amount(income.get("income_tax")))
    _put_detail(details, "provision_reversal", _present_sum(income, ("operating_reversals", "financial_reversals")))
    _put_detail(details, "exceptional_income", _present_sum(income, ("disposal_proceeds", "other_hao_income")))
    _put_detail(details, "exceptional_expense", _present_sum(income, ("disposal_book_value", "other_hao_charges", "employee_participation")))
    if any(_statement_amount(balance.get(key)) is not None for key in BALANCE_KEYS):
        _put_amount(attrs, "stock_value", _present_sum(balance, ("stock_goods", "stock_materials", "stock_wip", "stock_finished")) or Decimal("0"))
        _put_amount(attrs, "receivables", _statement_amount(balance.get("customers")) or Decimal("0"))
        _put_amount(attrs, "other_current_assets", _present_sum(balance, (
            "hao_assets", "supplier_advances", "other_receivables", "marketable_securities",
            "instruments_receivable", "translation_asset",
        )) or Decimal("0"))
        attrs["cash_in_hand"] = Decimal("0")
        _put_amount(attrs, "bank_balance", _statement_amount(balance.get("cash_and_banks")) or Decimal("0"))
        details["cash_detail_mode"] = "DETAIL"
        _put_amount(attrs, "land_building_value", _present_sum(balance, ("land", "buildings", "fixtures")) or Decimal("0"))
        _put_amount(attrs, "equipment_value", _statement_amount(balance.get("equipment")) or Decimal("0"))
        _put_amount(attrs, "vehicle_value", _statement_amount(balance.get("transport_equipment")) or Decimal("0"))
        _put_amount(attrs, "other_fixed_assets", _present_sum(balance, (
            "intangible_development", "intangible_rights", "intangible_goodwill", "intangible_other",
            "intangible_in_progress", "intangible_advances", "tangible_advances",
            "investments", "other_financial_assets",
        )) or Decimal("0"))
        details["fixed_assets_detail_mode"] = "DETAIL"
        _put_amount(attrs, "supplier_debt", _statement_amount(balance.get("suppliers")) or Decimal("0"))
        _put_amount(attrs, "tax_social_debt", _statement_amount(balance.get("tax_social")) or Decimal("0"))
        _put_amount(attrs, "ongoing_credit_balance", _present_sum(balance, (
            "borrowings", "lease_debt", "other_financial_debt", "financial_provisions",
            "discount_credit", "treasury_credit", "bank_overdraft",
        )) or Decimal("0"))
        long_term = _statement_amount(notes.get("debt_noncurrent"))
        attrs["long_term_debt"] = long_term if long_term is not None and long_term >= 0 else Decimal("0")
        attrs["shareholder_debt"] = Decimal("0")
        _put_amount(attrs, "short_term_debt", _present_sum(balance, (
            "hao_liabilities", "customer_advances", "other_liabilities", "short_provisions", "translation_liability",
        )) or Decimal("0"))
        equity = _present_sum(balance, (
            "capital", "share_premium", "revaluation", "reserves", "retained_earnings",
            "period_result", "investment_grants", "regulated_provisions",
        ))
        if equity is not None:
            details["declared_equity"] = format(equity, "f")
    if len(dated) > 1:
        previous = dated[1][1].get("income") if isinstance(dated[1][1].get("income"), dict) else {}
        _put_amount(attrs, "turnover_prev", _present_sum(previous, ("sales_goods", "sales_manufactured", "sales_services", "accessory_products")))
        read_result = _statement_amount(previous.get("net_result_read"))
        _put_amount(attrs, "net_result_prev", read_result if read_result is not None else _signed_sum(previous, _NET_TERMS), allow_negative=True)
