from apps.notifications.services import (
    _alert_subject,
    _client_nom_prenom,
    _subject_tail,
)


def test_client_nom_prenom_is_last_then_first():
    client = type("C", (), {"last_name": "Dupont", "first_name": "Jean"})()
    assert _client_nom_prenom(client) == "Dupont Jean"


def test_credit_subject_tail_is_name_dash_amount():
    meta = {
        "kind": "CREDIT",
        "client_nom_prenom": "Dupont Jean",
        "amount_label": "5 000 000 XOF",
        "reference": "DOS-2026-0001",
    }
    assert _subject_tail(meta) == "Dupont Jean - 5 000 000 XOF — DOS-2026-0001"
    assert _alert_subject("[FIN_FLOW] Dossier en attente", meta) == (
        "[FIN_FLOW] Dossier en attente — Dupont Jean - 5 000 000 XOF — DOS-2026-0001"
    )


def test_main_levee_subject_keeps_the_requested_action():
    meta = {
        "kind": "MAIN_LEVEE",
        "client_nom_prenom": "Dupont Jean",
        "reference": "ML-12",
    }
    assert _subject_tail(meta) == "Main levée - Dupont Jean — ML-12"
    assert _alert_subject("[FIN_FLOW] Dossier en attente", meta) == (
        "[FIN_FLOW] Dossier en attente — Main levée - Dupont Jean — ML-12"
    )


def test_dation_subject_keeps_the_requested_action():
    meta = {
        "kind": "DATION",
        "client_nom_prenom": "Koné Awa",
        "reference": "DAT-3",
    }
    assert _subject_tail(meta) == "Dation - Koné Awa — DAT-3"
    assert _alert_subject("[FIN_FLOW] Dossier rejeté", meta) == (
        "[FIN_FLOW] Dossier rejeté — Dation - Koné Awa — DAT-3"
    )


def test_collection_subject_names_the_client():
    meta = {
        "kind": "COLLECTION",
        "client_nom_prenom": "Dupont Jean",
        "reference": "CR-2026-00012",
    }
    assert _subject_tail(meta) == "Dupont Jean — CR-2026-00012"
