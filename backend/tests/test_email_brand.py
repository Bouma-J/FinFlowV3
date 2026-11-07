"""Charte des e-mails : les couleurs viennent de la filiale."""
from types import SimpleNamespace

from apps.notifications.email_brand import branded_shell, colors_for_tenant
from apps.notifications.services import _build_bodies


def _tenant():
    return SimpleNamespace(
        name="Filiale Nord",
        code="NORD",
        brand_primary="#112233",
        brand_secondary="#0a1520",
        brand_accent="#cc8800",
        brand_sidebar="#081018",
        brand_sidebar_text="#f5f5f5",
    )


def test_colors_follow_the_tenant_and_reject_invalid_values():
    colors = colors_for_tenant(
        SimpleNamespace(
            brand_primary="bleu",
            brand_secondary="#0a1520",
            brand_accent="#cc8800",
            brand_sidebar="#081018",
            brand_sidebar_text="#f5f5f5",
        )
    )
    assert colors["primary"] == "#0f9488"
    assert colors["accent"] == "#cc8800"


def test_workflow_mail_uses_tenant_colors():
    tenant = _tenant()
    _, html = _build_bodies(
        title="Dossier en attente",
        intro="Une étape vous attend.",
        meta={
            "process_label": "Crédit",
            "reference": "CR-1",
            "client_display": "",
            "detail_url": "https://finflow.example/dossiers/1",
            "details": [],
        },
        tenant=tenant,
    )
    assert "Filiale Nord" in html
    assert "#112233" in html
    assert "#cc8800" in html
    assert "#081018" in html
    assert "#0f9488" not in html


def test_shell_without_tenant_keeps_the_default_charter():
    html = branded_shell(None, "<p>Test</p>")
    assert "#084f4a" in html
    assert "#d4a017" in html
    assert "Filiale" not in html
