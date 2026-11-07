"""Couleurs d'e-mail tirées de la charte de la filiale."""
from __future__ import annotations

import re

from django.utils.html import escape

_HEX = re.compile(r"\A#[0-9A-Fa-f]{6}\Z")

DEFAULT_COLORS = {
    "primary": "#0f9488",
    "secondary": "#0d7a72",
    "accent": "#d4a017",
    "sidebar": "#084f4a",
    "sidebar_text": "#ffffff",
}


def _hex(value, fallback: str) -> str:
    text = (value or "").strip()
    return text if _HEX.fullmatch(text) else fallback


def colors_for_tenant(tenant) -> dict[str, str]:
    """Couleurs hex sûres. Une filiale absente reprend la charte par défaut."""
    if tenant is None:
        return dict(DEFAULT_COLORS)
    return {
        "primary": _hex(getattr(tenant, "brand_primary", None), DEFAULT_COLORS["primary"]),
        "secondary": _hex(getattr(tenant, "brand_secondary", None), DEFAULT_COLORS["secondary"]),
        "accent": _hex(getattr(tenant, "brand_accent", None), DEFAULT_COLORS["accent"]),
        "sidebar": _hex(getattr(tenant, "brand_sidebar", None), DEFAULT_COLORS["sidebar"]),
        "sidebar_text": _hex(
            getattr(tenant, "brand_sidebar_text", None), DEFAULT_COLORS["sidebar_text"]
        ),
    }


def _luminance(color: str) -> float:
    channel = color.lstrip("#")
    red = int(channel[0:2], 16)
    green = int(channel[2:4], 16)
    blue = int(channel[4:6], 16)
    return (0.2126 * red + 0.7152 * green + 0.0722 * blue) / 255


def readable_text(background: str, preferred: str) -> str:
    """Texte lisible sur le fond. La couleur préférée est gardée si le contraste suffit."""
    if abs(_luminance(background) - _luminance(preferred)) >= 0.35:
        return preferred
    return "#17231f" if _luminance(background) > 0.62 else "#ffffff"


def branded_shell(tenant, inner_html: str) -> str:
    """Enveloppe HTML : bandeau de la filiale, filet d'accent, contenu."""
    colors = colors_for_tenant(tenant)
    label = ""
    if tenant is not None:
        label = (getattr(tenant, "name", None) or getattr(tenant, "code", None) or "").strip()
    header = ""
    if label:
        header = (
            f'<div style="background:{colors["sidebar"]};color:{colors["sidebar_text"]};'
            f'padding:14px 18px;font-weight:600;">{escape(label)}</div>'
        )
    return f"""
    <div style="font-family:Segoe UI,Arial,sans-serif;font-size:14px;color:#17231f;max-width:560px;">
      {header}
      <div style="height:4px;background:{colors["accent"]};line-height:4px;">&nbsp;</div>
      <div style="padding:16px 18px 8px;">
        {inner_html}
      </div>
    </div>
    """
