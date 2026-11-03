"""Calculs d'analyse financière approfondie (contre-analyse) et scoring.

Regroupe l'ensemble des indicateurs dérivés (ratios de structure, de rotation,
de liquidité, rentabilité, stress test, quotité cessible) ainsi que la grille
de scoring pondérée. Les seuils utilisés proviennent de la filiale
(``AnalysisThreshold``) et restent donc paramétrables.
"""
from decimal import Decimal, InvalidOperation

Q2 = Decimal("0.01")

PERIODS_PER_YEAR = {
    "MONTHLY": Decimal("12"),
    "QUARTERLY": Decimal("4"),
    "ANNUAL": Decimal("1"),
}


def _dec(value):
    if value is None:
        return Decimal("0")
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _div(num, den):
    """Division tolérante : renvoie None si dénominateur nul."""
    num, den = _dec(num), _dec(den)
    if den == 0:
        return None
    return num / den


def _q(value):
    if value is None:
        return None
    try:
        return Decimal(value).quantize(Q2)
    except (InvalidOperation, TypeError, ValueError):
        return None


def _pct(num, den):
    r = _div(num, den)
    return r * Decimal("100") if r is not None else None


def _score_high(value, bad, good):
    """0 si <= bad, 100 si >= good, linéaire entre les deux (plus haut = mieux)."""
    if value is None:
        return None
    value, bad, good = _dec(value), _dec(bad), _dec(good)
    if good == bad:
        return Decimal("100") if value >= good else Decimal("0")
    ratio = (value - bad) / (good - bad) * Decimal("100")
    return max(Decimal("0"), min(Decimal("100"), ratio))


def _score_low(value, good, bad):
    """100 si <= good, 0 si >= bad, linéaire entre les deux (plus bas = mieux)."""
    if value is None:
        return None
    value, good, bad = _dec(value), _dec(good), _dec(bad)
    if bad == good:
        return Decimal("100") if value <= good else Decimal("0")
    ratio = (bad - value) / (bad - good) * Decimal("100")
    return max(Decimal("0"), min(Decimal("100"), ratio))


def guarantee_coverage(analysis):
    """Couverture (%) du crédit par la valeur retenue des garanties ACTIVE."""
    from .collateral import guarantee_coverage_retained

    return guarantee_coverage_retained(analysis)


def compute_metrics(analysis, th):
    """Renvoie l'ensemble des indicateurs dérivés + les drapeaux de conformité."""
    stress = _dec(th.stress_pct) / Decimal("100")
    ppy = PERIODS_PER_YEAR.get(analysis.reference_period, Decimal("12"))

    installment = _dec(analysis.new_installment)
    existing = _dec(analysis.existing_debt_monthly)
    global_service = installment + existing

    m = {}
    m["installment"] = _q(installment)
    m["existing_debt_monthly"] = _q(existing)
    m["global_debt_service"] = _q(global_service)
    m["guarantee_coverage"] = _q(guarantee_coverage(analysis))

    flags = {}

    if analysis.is_corporate:
        gross_margin = analysis.gross_margin
        cash_flow = analysis.cash_flow
        monthly_cash_flow = cash_flow * ppy / Decimal("12")
        annual_turnover = _dec(analysis.turnover) * ppy
        annual_cogs = _dec(analysis.cogs) * ppy
        annual_net = analysis.net_result * ppy

        current_assets = (
            _dec(analysis.stock_value) + _dec(analysis.receivables)
            + _dec(analysis.cash_available)
        )
        current_liabilities = (
            _dec(analysis.supplier_debt) + _dec(analysis.short_term_debt)
        )
        bfr = analysis.bfr
        fr = (
            analysis.equity + _dec(analysis.ongoing_credit_balance)
            - _dec(analysis.fixed_assets)
        )
        treasury_net = fr - bfr

        m.update({
            "monthly_cash_flow": _q(monthly_cash_flow),
            "annual_cash_flow": _q(cash_flow * ppy),
            "current_assets": _q(current_assets),
            "current_liabilities": _q(current_liabilities),
            "working_capital": _q(fr),
            "bfr": _q(bfr),
            "treasury_net": _q(treasury_net),
            "bfr_days": _q(
                _div(bfr, annual_turnover) * Decimal("360")
                if annual_turnover else None
            ),
            "dso_days": _q(
                _div(_dec(analysis.receivables), annual_turnover) * Decimal("360")
                if annual_turnover else None
            ),
            "dpo_days": _q(
                _div(_dec(analysis.supplier_debt), annual_cogs) * Decimal("360")
                if annual_cogs else None
            ),
            "dio_days": _q(
                _div(_dec(analysis.stock_value), annual_cogs) * Decimal("360")
                if annual_cogs else None
            ),
            "current_ratio": _q(_div(current_assets, current_liabilities)),
            "quick_ratio": _q(
                _div(current_assets - _dec(analysis.stock_value),
                     current_liabilities)
            ),
            "financial_autonomy": _q(_pct(analysis.equity, analysis.total_assets)),
            "gearing": _q(_div(_dec(analysis.ongoing_credit_balance),
                               analysis.equity)),
            "solvency_ratio": _q(analysis.debt_ratio),
            "interest_coverage": _q(_div(analysis.ebe,
                                         _dec(analysis.financial_charges))),
            "roe": _q(_pct(annual_net, analysis.equity)),
            "roa": _q(_pct(annual_net, analysis.total_assets)),
            "dscr": _q(_div(monthly_cash_flow, installment)),
            "global_dscr": _q(_div(monthly_cash_flow, global_service)),
            "dscr_stress": _q(
                _div(monthly_cash_flow * (Decimal("1") - stress), global_service)
            ),
            "turnover_growth": _q(
                _pct(_dec(analysis.turnover) - _dec(analysis.turnover_prev),
                     analysis.turnover_prev)
                if _dec(analysis.turnover_prev) else None
            ),
            "result_growth": _q(
                _pct(analysis.net_result - _dec(analysis.net_result_prev),
                     analysis.net_result_prev)
                if _dec(analysis.net_result_prev) else None
            ),
            "safety_margin": _q(monthly_cash_flow - global_service),
        })

        # Point mort (seuil de rentabilité) sur charges fixes / taux de marge.
        gm_rate = _div(gross_margin, analysis.turnover)
        fixed_costs = (
            analysis.total_operating_expenses + _dec(analysis.depreciation)
            + _dec(analysis.financial_charges)
        )
        m["break_even_turnover"] = _q(
            _div(fixed_costs, gm_rate) if gm_rate else None
        )

        flags = {
            "dscr_ok": _cmp_ge(m["global_dscr"], th.min_dscr),
            "dscr_stress_ok": _cmp_ge(m["dscr_stress"], th.min_dscr),
            "leverage_ok": _cmp_le(m["solvency_ratio"], th.max_leverage_ratio),
            "gearing_ok": _cmp_le(m["gearing"], th.max_gearing),
            "autonomy_ok": _cmp_ge(m["financial_autonomy"],
                                   th.min_financial_autonomy),
            "current_ratio_ok": _cmp_ge(m["current_ratio"], th.min_current_ratio),
            "interest_coverage_ok": _cmp_ge(m["interest_coverage"],
                                            th.min_interest_coverage),
            "guarantee_ok": _cmp_ge(m["guarantee_coverage"],
                                    th.min_guarantee_coverage),
        }
    elif analysis.is_groupement:
        collective_income = (
            _dec(analysis.collective_contributions)
            + _dec(analysis.collective_other_income)
            + _dec(analysis.group_activity_turnover)
        )
        collective_charges = (
            _dec(analysis.collective_operating_expenses)
            + _dec(analysis.group_activity_expenses)
        )
        net_capacity = analysis.collective_capacity - existing
        stressed = collective_income * (Decimal("1") - stress)

        m.update({
            "collective_income": _q(collective_income),
            "collective_charges": _q(collective_charges),
            "collective_capacity": _q(analysis.collective_capacity),
            "collective_net_capacity": _q(net_capacity),
            "debt_ratio": _q(_pct(global_service, collective_income)),
            "debt_ratio_stress": _q(_pct(global_service, stressed)),
            "safety_margin": _q(net_capacity - installment),
            "members_count": analysis.members_count,
            "active_contributing_members": analysis.active_contributing_members,
            "solidarity_commitment": analysis.solidarity_commitment,
        })
        concentration = None
        if analysis.members_count and analysis.active_contributing_members:
            concentration = _pct(
                analysis.active_contributing_members, analysis.members_count
            )
        m["contribution_concentration"] = _q(concentration)

        flags = {
            "debt_ratio_ok": _cmp_le(m["debt_ratio"], th.max_debt_ratio),
            "debt_ratio_stress_ok": _cmp_le(
                m["debt_ratio_stress"], th.max_debt_ratio
            ),
            "capacity_ok": net_capacity > 0,
            "members_ok": bool(
                analysis.members_count and analysis.members_count > 0
            ),
            "solidarity_ok": analysis.solidarity_commitment,
            "guarantee_ok": _cmp_ge(
                m["guarantee_coverage"], th.min_guarantee_coverage
            ),
        }
    else:
        income = analysis.total_income
        stable_income = (
            _dec(analysis.salary_income) + _dec(analysis.spouse_income)
            + _dec(analysis.rental_income)
        )
        weight = analysis.informal_income_weight
        weight = _dec(weight) if weight is not None else _dec(th.informal_income_weight)
        weighted_income = stable_income + (
            _dec(analysis.other_activity_income) + _dec(analysis.other_income)
        ) * weight / Decimal("100")
        if analysis.has_side_activity:
            weighted_income += analysis.activity_net * weight / Decimal("100")

        stressed_income = income * (Decimal("1") - stress)
        frac = _dec(th.transferable_quota_fraction) / Decimal("100")
        quota_amount = _dec(analysis.net_salary) * frac
        quota_available = quota_amount - _dec(analysis.salary_deductions)

        m.update({
            "weighted_income": _q(weighted_income),
            "activity_net": _q(analysis.activity_net)
            if analysis.has_side_activity else None,
            "residual_after_loan": _q(analysis.disposable_income - installment),
            "debt_ratio": _q(_pct(global_service, income)),
            "debt_ratio_weighted": _q(_pct(global_service, weighted_income)),
            "debt_ratio_stress": _q(_pct(global_service, stressed_income)),
            "transferable_quota_amount": _q(quota_amount),
            "transferable_quota_available": _q(quota_available),
            "safety_margin": _q(analysis.disposable_income - installment),
            "disposable_per_capita": _q(analysis.disposable_per_capita),
        })

        flags = {
            "debt_ratio_ok": _cmp_le(m["debt_ratio"], th.max_debt_ratio),
            "debt_ratio_stress_ok": _cmp_le(m["debt_ratio_stress"],
                                            th.max_debt_ratio),
            "disposable_ok": analysis.disposable_income > 0,
            "living_wage_ok": (
                _cmp_ge(m["disposable_per_capita"], th.min_living_wage_per_capita)
                if _dec(th.min_living_wage_per_capita) > 0 else None
            ),
            "quota_ok": (
                installment <= quota_available
                if _dec(analysis.net_salary) > 0 else None
            ),
            "guarantee_ok": _cmp_ge(m["guarantee_coverage"],
                                    th.min_guarantee_coverage),
        }

    m["flags"] = flags
    return m


def _cmp_ge(value, threshold):
    if value is None:
        return None
    return _dec(value) >= _dec(threshold)


def _cmp_le(value, threshold):
    if value is None:
        return None
    return _dec(value) <= _dec(threshold)


def _history_score(analysis):
    """Score historique (0-100) : incidents, taux de remboursement, retards."""
    score = Decimal("100")
    if analysis.has_payment_incidents:
        score -= Decimal("40")
    rate = analysis.prior_repayment_rate
    if rate is not None:
        # Un taux < 100 % pénalise proportionnellement.
        score = min(score, _dec(rate))
    delay = analysis.prior_max_delay_days or analysis.max_days_late
    if delay:
        score -= min(Decimal("40"), _dec(delay))
    return max(Decimal("0"), min(Decimal("100"), score))


def compute_score(analysis, m, th):
    """Grille de scoring pondérée → (score /100, détail par composante)."""
    parts = []

    guarantee_s = _score_high(
        m.get("guarantee_coverage"),
        bad=Decimal("50"),
        good=_dec(th.min_guarantee_coverage) * Decimal("1.2"),
    )
    history_s = _history_score(analysis)

    if analysis.is_corporate:
        capacity_s = _score_high(m.get("global_dscr"), bad=Decimal("1"),
                                 good=_dec(th.min_dscr) * Decimal("1.6"))
        debt_s = _score_low(m.get("gearing"), good=Decimal("0.5"),
                            bad=_dec(th.max_gearing))
        autonomy_s = _score_high(m.get("financial_autonomy"), bad=Decimal("0"),
                                 good=_dec(th.min_financial_autonomy) * Decimal("2"))
        liquidity_s = _score_high(m.get("current_ratio"), bad=Decimal("0.5"),
                                  good=_dec(th.min_current_ratio) * Decimal("1.5"))
        structure_s = _avg([autonomy_s, liquidity_s])
        parts = [
            ("capacity", "Capacité de remboursement (DSCR)", capacity_s, 30),
            ("debt", "Endettement / gearing", debt_s, 20),
            ("structure", "Structure financière", structure_s, 20),
            ("guarantee", "Garanties réelles", guarantee_s, 15),
            ("history", "Historique de remboursement", history_s, 15),
        ]
    elif analysis.is_groupement:
        capacity_s = _score_low(
            m.get("debt_ratio"),
            good=_dec(th.max_debt_ratio) * Decimal("0.5"),
            bad=_dec(th.max_debt_ratio) * Decimal("1.25"),
        )
        debt_s = _score_low(
            m.get("debt_ratio_stress"),
            good=_dec(th.max_debt_ratio) * Decimal("0.6"),
            bad=_dec(th.max_debt_ratio) * Decimal("1.4"),
        )
        solidarity_s = (
            Decimal("100") if analysis.solidarity_commitment else Decimal("40")
        )
        concentration = m.get("contribution_concentration")
        concentration_s = _score_high(
            concentration, bad=Decimal("20"), good=Decimal("80")
        )
        structure_s = _avg([solidarity_s, concentration_s])
        parts = [
            ("capacity", "Capacité collective", capacity_s, 35),
            ("debt", "Effort collectif sous stress", debt_s, 20),
            ("structure", "Solidarité & cotisations", structure_s, 15),
            ("guarantee", "Garanties réelles", guarantee_s, 15),
            ("history", "Historique de remboursement", history_s, 15),
        ]
    else:
        capacity_s = _score_low(m.get("debt_ratio"),
                                good=_dec(th.max_debt_ratio) * Decimal("0.5"),
                                bad=_dec(th.max_debt_ratio) * Decimal("1.25"))
        debt_s = _score_low(m.get("debt_ratio_stress"),
                            good=_dec(th.max_debt_ratio) * Decimal("0.6"),
                            bad=_dec(th.max_debt_ratio) * Decimal("1.4"))
        # Stabilité : quotité respectée + ancienneté.
        quota_ok = m.get("flags", {}).get("quota_ok")
        stability_s = Decimal("60")
        if quota_ok is True:
            stability_s = Decimal("100")
        elif quota_ok is False:
            stability_s = Decimal("20")
        seniority = analysis.employment_seniority_months
        if seniority is not None:
            stability_s = _avg([
                stability_s,
                _score_high(seniority, bad=Decimal("0"), good=Decimal("24")),
            ])
        parts = [
            ("capacity", "Taux d'effort / reste à vivre", capacity_s, 35),
            ("debt", "Endettement sous stress", debt_s, 20),
            ("stability", "Stabilité & quotité", stability_s, 15),
            ("guarantee", "Garanties réelles", guarantee_s, 15),
            ("history", "Historique de remboursement", history_s, 15),
        ]

    total_weight = Decimal("0")
    weighted = Decimal("0")
    breakdown = []
    for key, label, value, weight in parts:
        w = Decimal(weight)
        if value is None:
            breakdown.append({
                "key": key, "label": label, "score": None, "weight": weight,
            })
            continue
        total_weight += w
        weighted += _dec(value) * w
        breakdown.append({
            "key": key, "label": label,
            "score": float(_dec(value).quantize(Q2)), "weight": weight,
        })

    score = (weighted / total_weight) if total_weight else None
    return (_q(score), {"total": float(_q(score)) if score is not None else None,
                        "components": breakdown})


def _avg(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    return sum(vals, Decimal("0")) / Decimal(len(vals))
