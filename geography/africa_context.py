from __future__ import annotations

import re
import unicodedata
from typing import Any

# Ce registre classe uniquement les pays par sous-région africaine.
# Il ne déduit aucune maladie, épidémie ou niveau de risque sanitaire.
_SUBREGIONS: dict[str, set[str]] = {
    "Afrique centrale": {
        "angola", "cameroun", "cameroon", "republique centrafricaine",
        "central african republic", "tchad", "chad", "congo",
        "republique du congo", "republique democratique du congo",
        "rdc", "drc", "guinee equatoriale", "equatorial guinea",
        "gabon", "sao tome et principe",
    },
    "Afrique de l'Ouest": {
        "benin", "burkina faso", "cap vert", "cabo verde", "cote d ivoire",
        "ivory coast", "gambie", "gambia", "ghana", "guinee", "guinea",
        "guinee bissau", "liberia", "mali", "mauritanie", "mauritania",
        "niger", "nigeria", "senegal", "sierra leone", "togo",
    },
    "Afrique de l'Est": {
        "burundi", "djibouti", "erythree", "eritrea", "ethiopie", "ethiopia",
        "kenya", "rwanda", "somalie", "somalia", "soudan du sud",
        "south sudan", "soudan", "sudan", "tanzanie", "tanzania", "ouganda",
        "uganda",
    },
    "Afrique australe": {
        "afrique du sud", "south africa", "botswana", "eswatini", "lesotho",
        "malawi", "mozambique", "namibie", "namibia", "zambie", "zambia",
        "zimbabwe",
    },
    "Afrique du Nord": {
        "algerie", "algeria", "egypte", "egypt", "libye", "libya", "maroc",
        "morocco", "tunisie", "tunisia",
    },
    "Océan Indien africain": {
        "comores", "comoros", "madagascar", "maurice", "mauritius",
        "seychelles",
    },
}


def _normalize(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value.strip().lower())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def normalize_country(country: str | None) -> str | None:
    value = " ".join((country or "").strip().split())
    return value or None


def infer_african_subregion(country: str | None) -> str | None:
    key = _normalize(country)
    if not key:
        return None
    for subregion, countries in _SUBREGIONS.items():
        if key in countries:
            return subregion
    return None


def build_africa_context(
    *,
    country: str | None,
    administrative_region: str | None = None,
    health_zone: str | None = None,
    environment: str | None = None,
    season: str | None = None,
    recent_travel: list[str] | None = None,
    endemic_conditions: list[str] | None = None,
    active_health_alerts: list[str] | None = None,
    source_date: str | None = None,
) -> dict[str, Any]:
    """Construit un contexte explicite sans inventer de données sanitaires.

    Les maladies endémiques et alertes actives doivent être fournies par une
    source administrative, un opérateur autorisé ou un service actualisé.
    """
    return {
        "country": normalize_country(country),
        "african_subregion": infer_african_subregion(country),
        "administrative_region": administrative_region or None,
        "health_zone": health_zone or None,
        "environment": environment or None,
        "season": season or None,
        "recent_travel": [item for item in (recent_travel or []) if item],
        "endemic_conditions": [item for item in (endemic_conditions or []) if item],
        "active_health_alerts": [item for item in (active_health_alerts or []) if item],
        "source_date": source_date or None,
        "context_policy": (
            "Utiliser uniquement les éléments transmis. Ne pas inventer une "
            "maladie endémique, une épidémie ou une alerte sanitaire."
        ),
    }
