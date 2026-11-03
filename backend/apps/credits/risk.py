"""Dérivation du niveau de risque workflow depuis l'analyse de référence."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation


def _dec(value) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None


def risk_level_from_analysis(analysis) -> int | None:
    """
    Mappe l'analyse de référence vers risk_level (1–5) pour le circuit.

    Priorité : recommendation, sinon score interne (/100).
    """
    if analysis is None:
        return None

    rec = (getattr(analysis, "recommendation", None) or "").upper()
    if rec == "UNFAVORABLE":
        return 5
    if rec == "CONDITIONAL":
        return 3
    if rec == "FAVORABLE":
        return 2

    score = _dec(getattr(analysis, "internal_score", None))
    if score is None:
        return None
    if score >= 80:
        return 1
    if score >= 65:
        return 2
    if score >= 50:
        return 3
    if score >= 35:
        return 4
    return 5
