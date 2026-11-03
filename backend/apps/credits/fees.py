"""Calcul et agrégation des frais d'un dossier de crédit."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from .amounts import reference_amount


def _dec(value) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def fees_base_amount(application) -> Decimal | None:
    """Base de calcul des % : montant de référence du dossier."""
    return reference_amount(application)


def build_fees_breakdown(application) -> dict:
    """
    Liste des frais (dossier + additionnels) avec montants calculés et total.

    Les frais sont exprimés pour information / contractualisation. Ils sont
    prélevés par le CBS sur le montant décaissé (montant accordé) — Fin Flow
    débourse le montant accordé intégral, sans soustraction locale.
    """
    base = fees_base_amount(application)
    lines = []

    dossier_rate = _dec(getattr(application, "fees_rate", None))
    if dossier_rate is not None:
        amount = _money(base * dossier_rate / Decimal("100")) if base is not None else None
        lines.append(
            {
                "id": None,
                "label": "Frais de dossier",
                "mode": "PERCENT",
                "value": str(dossier_rate),
                "amount": str(amount) if amount is not None else None,
                "is_dossier": True,
            }
        )

    for fee in application.extra_fees.all():
        value = _dec(fee.value) or Decimal("0")
        if fee.mode == fee.Mode.PERCENT:
            amount = (
                _money(base * value / Decimal("100")) if base is not None else None
            )
        else:
            amount = _money(value)
        lines.append(
            {
                "id": str(fee.id),
                "label": fee.label,
                "mode": fee.mode,
                "value": str(value),
                "amount": str(amount) if amount is not None else None,
                "is_dossier": False,
            }
        )

    total = Decimal("0")
    has_amount = False
    for line in lines:
        if line["amount"] is not None:
            total += Decimal(line["amount"])
            has_amount = True

    net_after_fees = None
    if base is not None and has_amount:
        net_after_fees = _money(base - total)

    return {
        "base_amount": str(base) if base is not None else None,
        "lines": lines,
        "total": str(_money(total)) if has_amount else None,
        "net_after_fees": str(net_after_fees) if net_after_fees is not None else None,
    }


def sync_extra_fees(application, payload) -> None:
    """Remplace les frais additionnels à partir d'une liste JSON."""
    from .models import CreditApplicationFee

    if payload is None:
        return
    if isinstance(payload, str):
        import json

        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError("Liste de frais invalide.") from exc
    if not isinstance(payload, list):
        raise ValueError("Une liste de frais est attendue.")

    application.extra_fees.all().delete()
    for idx, raw in enumerate(payload):
        if not isinstance(raw, dict):
            continue
        label = (raw.get("label") or "").strip()
        if not label:
            continue
        mode = (raw.get("mode") or CreditApplicationFee.Mode.AMOUNT).upper()
        if mode not in CreditApplicationFee.Mode.values:
            mode = CreditApplicationFee.Mode.AMOUNT
        value = _dec(raw.get("value"))
        if value is None:
            continue
        CreditApplicationFee.objects.create(
            tenant_id=application.tenant_id,
            application=application,
            label=label[:150],
            mode=mode,
            value=value,
            sort_order=idx,
        )
