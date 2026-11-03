"""Décaissement crédit via API Perfect (POST …/crd/simple)."""
from __future__ import annotations

import logging
from decimal import Decimal

from django.conf import settings

from .models import CoreBankingConnector, IntegrationLog
from .perfect_defaults import PERIODICITY_CBS
from .services import (
    CoreBankingError,
    OP_SUBMIT_CREDIT,
    _require_success,
    resolve_active_connector,
    send_operation,
)

logger = logging.getLogger("finflow")

DEFAULT_CRD_SIMPLE_PATH = "gateway-perfect/crd/simple"


def _disbursement_rules(connector: CoreBankingConnector) -> dict:
    return (connector.mapping_rules or {}).get("disbursement") or {}


def disbursement_mode(connector: CoreBankingConnector) -> str:
    """
    ``CBS`` (défaut si REST + URL) ou ``LOCAL`` (pas d'appel Perfect).

    Configurable via ``mapping_rules.disbursement.mode``.
    """
    rules = _disbursement_rules(connector)
    mode = str(rules.get("mode") or "").strip().upper()
    if mode in {"CBS", "LOCAL"}:
        return mode
    # Heuristique : sans URL réelle → local (simulation / démo).
    if not (connector.base_url or "").strip():
        return "LOCAL"
    if (connector.mapping_rules or {}).get("force_simulate"):
        return "LOCAL"
    return "CBS"


def build_callback_url(application) -> str:
    base = (
        getattr(settings, "PUBLIC_API_BASE_URL", None)
        or getattr(settings, "FRONTEND_BASE_URL", None)
        or "http://localhost:8000"
    ).rstrip("/")
    # Si FRONTEND_BASE_URL pointe vers Vite, préférer une URL API explicite.
    if base.endswith(":5173"):
        base = base.replace(":5173", ":8000")
    return f"{base}/api/v1/cbs/callbacks/crd/{application.pk}/"


def build_credit_disbursement_payload(application, *, connector=None) -> dict:
    """Construit le corps Perfect ``crd/simple`` à partir du dossier."""
    from apps.credits.amounts import reference_amount
    from apps.credits.services import period_count

    client = application.client
    product = application.product
    if client is None:
        raise CoreBankingError("Client manquant pour le décaissement CBS.")
    if product is None:
        raise CoreBankingError("Produit manquant pour le décaissement CBS.")

    connector = connector or resolve_active_connector(application.tenant_id)
    rules = _disbursement_rules(connector)
    defaults = rules.get("defaults") or {}
    # Maps syncées du connecteur uniquement (pas de re-fusion PURPOSE_CBS legacy)
    purpose_map = dict(rules.get("purpose_map") or {})
    periodicity_map = dict(rules.get("periodicity_map") or {})
    if not periodicity_map:
        periodicity_map = dict(PERIODICITY_CBS)

    code_adherent = (client.cbs_client_id or "").strip()
    num_manuel = (client.cbs_account_number or "").strip()
    num_piece = (getattr(client, "national_id", None) or "").strip()
    if not (code_adherent or num_manuel or num_piece):
        raise CoreBankingError(
            "Identifiant adhérent CBS manquant sur le client "
            "(cbs_client_id / cbs_account_number / pièce d'identité). "
            "Importez ou renseignez la situation CBS avant décaissement."
        )

    agency = application.agency
    id_point = (
        (getattr(agency, "cbs_point_of_service_id", None) or "").strip()
        or str(defaults.get("idPointService") or "").strip()
    )
    if not id_point:
        raise CoreBankingError(
            "Point de service CBS manquant : renseignez "
            "cbs_point_of_service_id sur l'agence, ou "
            "mapping_rules.disbursement.defaults.idPointService."
        )

    id_produit_crd = (
        (product.cbs_product_code or "").strip()
        or str(defaults.get("idProduitCrd") or product.code or "").strip()
    )
    if not id_produit_crd:
        raise CoreBankingError(
            "Code produit crédit CBS (idProduitCrd) manquant sur le produit."
        )

    from apps.catalog.cbs_resolve import (
        resolve_currency_cbs,
        resolve_periodicity_cbs,
        resolve_repayment_cbs,
    )

    id_produit_remb = (
        (product.cbs_repayment_product_code or "").strip()
        or resolve_repayment_cbs(
            application.tenant_id, application.repayment_mechanism or ""
        )
        or str(defaults.get("idProduitRemb") or "").strip()
    )
    if not id_produit_remb:
        raise CoreBankingError(
            "Code produit remboursement CBS (idProduitRemb) manquant "
            "(méthode de remboursement, produit ou "
            "mapping_rules.disbursement.defaults)."
        )

    id_gestionnaire = ""
    for actor in (
        getattr(application, "submitted_by", None),
        getattr(application, "created_by", None),
    ):
        if actor is None:
            continue
        # Uniquement l'id gestionnaire CBS (pas le matricule RH)
        id_gestionnaire = (getattr(actor, "cbs_id", None) or "").strip()
        if id_gestionnaire:
            break
    if not id_gestionnaire:
        id_gestionnaire = str(defaults.get("idGestionnaire") or "").strip()
    if not id_gestionnaire:
        raise CoreBankingError(
            "Identifiant gestionnaire CBS (idGestionnaire) manquant : "
            "associez un gestionnaire CBS à l'utilisateur soumissionnaire, "
            "ou mapping_rules.disbursement.defaults.idGestionnaire."
        )

    periodicity = application.periodicity or "MONTHLY"
    id_periodicite = resolve_periodicity_cbs(
        application.tenant_id,
        periodicity,
        fallback_map=periodicity_map,
    )
    purpose_type = application.purpose_type or "OTHER"
    from apps.catalog.cbs_resolve import resolve_financing_object_cbs

    id_objet = resolve_financing_object_cbs(
        application.tenant_id,
        purpose_type,
        purpose_map=purpose_map,
        default=str(defaults.get("idObjetFinancement") or ""),
    )
    if not id_objet:
        raise CoreBankingError(
            "Objet de financement CBS (idObjetFinancement) manquant : "
            "importez les objets Perfect et associez un PurposeType, "
            "ou renseignez purpose_map / defaults.idObjetFinancement."
        )

    amount = reference_amount(application) or application.amount_requested
    if amount is None:
        raise CoreBankingError("Montant à décaisser introuvable.")

    rate = application.interest_rate
    if rate is None and product.interest_rate is not None:
        rate = product.interest_rate
    if rate is None:
        raise CoreBankingError("Taux d'intérêt manquant pour le décaissement CBS.")

    n_echeances = int(
        period_count(
            application.duration_months or 1,
            periodicity,
            tenant_id=application.tenant_id,
        )
    )
    external_id = (application.reference or str(application.pk)).strip()
    currency = resolve_currency_cbs(
        application.tenant_id,
        application.currency
        or getattr(product, "currency", None)
        or "XOF",
    )

    payload = {
        "externalId": external_id,
        "callbackUrl": build_callback_url(application),
        "idPointService": id_point,
        "idPeriodicite": id_periodicite,
        "taux": float(Decimal(rate)),
        "nombreEcheance": n_echeances,
        "idObjetFinancement": id_objet,
        "idGestionnaire": id_gestionnaire,
        "idProduitCrd": id_produit_crd,
        "idProduitRemb": id_produit_remb,
        "montantDemande": float(Decimal(amount)),
        "codeDevise": currency,
    }
    if code_adherent:
        payload["codeAdherent"] = code_adherent
    if num_manuel:
        payload["numManuel"] = num_manuel
    if num_piece:
        payload["numPieceIdentite"] = num_piece
    return payload


def submit_credit_to_cbs(application, *, connector=None) -> dict:
    """
    Envoie la demande de crédit / décaissement au CBS (Perfect crd/simple).

    Retour normalisé :
    {
      mode, external_id, num_demande, ref_demande, num_contrat,
      limit_credit, montant, currency, raw, log_id, external_reference
    }
    """
    connector = connector or resolve_active_connector(application.tenant_id)
    mode = disbursement_mode(connector)

    if mode == "LOCAL":
        payload = build_credit_disbursement_payload(
            application, connector=connector
        )
        idem = f"disburse:{application.pk}"
        existing = IntegrationLog.all_tenants.filter(
            connector=connector,
            idempotency_key=idem,
            status=IntegrationLog.Status.SUCCESS,
        ).first()
        if existing:
            response = existing.response_payload or {}
            raw = response.get("raw") or response
            return {
                "mode": "LOCAL",
                "external_id": payload["externalId"],
                "num_demande": str(
                    response.get("num_demande") or raw.get("numDemande") or ""
                ),
                "ref_demande": str(
                    response.get("ref_demande") or raw.get("refDemande") or ""
                ),
                "num_contrat": str(
                    response.get("num_contrat")
                    or raw.get("numContrat")
                    or existing.external_reference
                    or ""
                ),
                "limit_credit": response.get("limit_credit") or raw.get("limitCredit"),
                "montant": response.get("montant") or raw.get("montant"),
                "currency": payload["codeDevise"],
                "raw": raw,
                "log_id": str(existing.id),
                "external_reference": existing.external_reference,
                "payload_sent": payload,
            }

        from .services import SimulatedAdapter

        response = SimulatedAdapter(connector).send(OP_SUBMIT_CREDIT, payload)
        log = IntegrationLog.all_tenants.create(
            tenant_id=application.tenant_id,
            connector=connector,
            operation=OP_SUBMIT_CREDIT,
            direction=IntegrationLog.Direction.OUTBOUND,
            idempotency_key=idem,
            request_payload=payload,
            response_payload=response,
            status=IntegrationLog.Status.SUCCESS,
            external_reference=response.get("external_reference") or "",
            attempts=1,
        )
        return {
            "mode": "LOCAL",
            "external_id": payload["externalId"],
            "num_demande": response.get("num_demande") or "",
            "ref_demande": response.get("ref_demande") or "",
            "num_contrat": response.get("num_contrat")
            or response.get("external_reference")
            or "",
            "limit_credit": response.get("limit_credit"),
            "montant": response.get("montant"),
            "currency": payload["codeDevise"],
            "raw": response.get("raw") or response,
            "log_id": str(log.id),
            "external_reference": response.get("external_reference") or "",
            "payload_sent": payload,
        }

    payload = build_credit_disbursement_payload(application, connector=connector)
    idem = f"disburse:{application.pk}"
    log = send_operation(
        connector,
        OP_SUBMIT_CREDIT,
        payload,
        idempotency_key=idem,
    )
    response = _require_success(log, OP_SUBMIT_CREDIT)
    raw = response.get("raw") or response
    return {
        "mode": "CBS",
        "external_id": payload["externalId"],
        "num_demande": str(
            response.get("num_demande") or raw.get("numDemande") or ""
        ),
        "ref_demande": str(
            response.get("ref_demande") or raw.get("refDemande") or ""
        ),
        "num_contrat": str(
            response.get("num_contrat")
            or raw.get("numContrat")
            or log.external_reference
            or ""
        ),
        "limit_credit": response.get("limit_credit") or raw.get("limitCredit"),
        "montant": response.get("montant") or raw.get("montant"),
        "currency": payload["codeDevise"],
        "raw": raw,
        "log_id": str(log.id),
        "external_reference": log.external_reference,
        "payload_sent": payload,
    }


def apply_cbs_callback(application_id, body: dict, *, secret: str | None = None):
    """Traite un callback Perfect sur une demande de crédit."""
    from django.db import transaction

    from apps.credits.models import CreditApplication, Loan

    with transaction.atomic():
        app = (
            CreditApplication.all_tenants.select_for_update()
            .filter(pk=application_id)
            .first()
        )
        if app is None:
            raise CoreBankingError("Dossier introuvable pour ce callback CBS.")

        connector = resolve_active_connector(app.tenant_id)
        expected = str(
            (_disbursement_rules(connector).get("callback_secret") or "")
        ).strip()
        # Secret obligatoire : refuse les callbacks anonymes même hors CBS live.
        if not expected:
            raise CoreBankingError(
                "Callback CBS refusé : configurez callback_secret sur le connecteur."
            )
        if not secret or secret != expected:
            raise CoreBankingError("Secret de callback CBS invalide.")

        # États vraiment terminaux : ignorer les replays. DISBURSED reste
        # ouvert aux mises à jour CBS (n° contrat, statut déblocage…).
        hard_terminal = {
            CreditApplication.Status.CLOSED,
            CreditApplication.Status.CANCELLED,
            CreditApplication.Status.REJECTED,
        }
        if app.status in hard_terminal:
            return {
                "application_id": str(app.pk),
                "loan_id": None,
                "ignored": True,
                "detail": f"Dossier déjà en statut {app.status} — callback ignoré.",
            }

        loan = (
            Loan.all_tenants.select_for_update()
            .filter(application_id=app.pk)
            .first()
        )
        status = str(
            body.get("status")
            or body.get("context")
            or body.get("responseCode")
            or "UPDATED"
        )[:40]
        updates = {
            "cbs_disbursement_status": status,
            "cbs_disbursement_payload": body if isinstance(body, dict) else {},
        }
        if body.get("numDemande"):
            updates["cbs_demande_number"] = str(body["numDemande"])[:100]
        if body.get("refDemande"):
            updates["cbs_demande_ref"] = str(body["refDemande"])[:100]
        if body.get("numContrat"):
            updates["cbs_contract_number"] = str(body["numContrat"])[:100]
            updates["core_banking_reference"] = str(body["numContrat"])[:100]

        if loan is not None:
            for k, v in updates.items():
                setattr(loan, k, v)
            loan.save(update_fields=[*updates.keys(), "updated_at"])

        app_updates = {}
        if body.get("numDemande"):
            app_updates["cbs_demande_number"] = str(body["numDemande"])[:100]
        if body.get("refDemande"):
            app_updates["cbs_demande_ref"] = str(body["refDemande"])[:100]
        if body.get("numContrat"):
            app_updates["cbs_contract_number"] = str(body["numContrat"])[:100]
        op_date = None
        raw_date = body.get("dateOperation")
        if raw_date:
            from datetime import date as date_cls

            try:
                op_date = date_cls.fromisoformat(str(raw_date).strip()[:10])
            except ValueError:
                op_date = None
        if op_date is not None:
            app_updates["cbs_operation_date"] = op_date
        if app_updates:
            for k, v in app_updates.items():
                setattr(app, k, v)
            app.save(update_fields=[*app_updates.keys(), "updated_at"])

        loan_id = str(loan.pk) if loan else None

    # Journal INBOUND hors du verrou dossier (échec non bloquant)
    try:
        connector = resolve_active_connector(app.tenant_id)
        IntegrationLog.all_tenants.create(
            tenant_id=app.tenant_id,
            connector=connector,
            operation="CRD_CALLBACK",
            direction=IntegrationLog.Direction.INBOUND,
            request_payload=body if isinstance(body, dict) else {"raw": body},
            response_payload={"application_id": str(app.pk)},
            status=IntegrationLog.Status.SUCCESS,
            external_reference=str(
                body.get("numContrat") or body.get("refDemande") or ""
            )[:100],
            attempts=1,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Échec journalisation callback CBS")

    return {"application_id": str(app.pk), "loan_id": loan_id}
