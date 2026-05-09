from __future__ import annotations

import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status

from app.core.config import get_settings

# Dossier des moteurs AlloDocteur.
# Les anciens fichiers moteur utilisent des imports absolus entre eux
# (ex. import allo_doc_triage_engine_v3_7_africa). On ajoute donc ce dossier
# au sys.path pour garder la compatibilité sans modifier 1000 lignes d'historique.
ENGINE_DIR = Path(__file__).resolve().parents[1] / "core" / "engine"
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

try:
    import allo_doc_triage_engine_v3_8_production_CONSOLIDATED as engine
except Exception as exc:
    engine = None  # type: ignore
    ENGINE_IMPORT_ERROR = exc
else:
    ENGINE_IMPORT_ERROR = None

_KB: dict[str, Any] | None = None
_KB_ERROR: Exception | None = None

DISCLAIMER = (
    "Ce service fournit une orientation de triage et ne remplace pas un diagnostic médical. "
    "En cas d'urgence vitale, appelez les urgences ou rendez-vous immédiatement à l'hôpital."
)


def load_kb_once(force: bool = False) -> dict[str, Any] | None:
    global _KB, _KB_ERROR
    if _KB is not None and not force:
        return _KB
    if engine is None:
        return None

    settings = get_settings()
    kb_path = settings.kb_file
    try:
        if not kb_path.exists():
            raise FileNotFoundError(
                f"Base de connaissances introuvable: {kb_path}. "
                "Ajoute data/kb_allodocteur_v3_complete.json ou définis ALLODOCTEUR_KB_PATH."
            )
        _KB = engine.load_kb(str(kb_path))
        _KB_ERROR = None
        return _KB
    except Exception as exc:
        _KB_ERROR = exc
        _KB = None
        return None


def engine_status() -> dict[str, Any]:
    settings = get_settings()
    kb = load_kb_once()
    return {
        "engine_loaded": engine is not None,
        "engine_error": str(ENGINE_IMPORT_ERROR) if ENGINE_IMPORT_ERROR else None,
        "kb_loaded": kb is not None,
        "kb_error": str(_KB_ERROR) if _KB_ERROR else None,
        "kb_path": str(settings.kb_file),
        "engine_dir": str(ENGINE_DIR),
    }


def make_json_safe(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if is_dataclass(obj):
        return make_json_safe(asdict(obj))
    if isinstance(obj, dict):
        return {str(k): make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [make_json_safe(x) for x in obj]
    if hasattr(obj, "__dict__"):
        return make_json_safe(vars(obj))
    return str(obj)


def run_triage(payload: dict[str, Any], dynamic_answers: dict[str, Any] | None = None) -> dict[str, Any]:
    if engine is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Moteur non chargé: {ENGINE_IMPORT_ERROR}")
    kb = load_kb_once()
    if kb is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Base de connaissances non chargée: {_KB_ERROR}")
    try:
        result = engine.run_triage_v3_8_production(payload, kb, dynamic_answers=dynamic_answers or {})
        return make_json_safe(result)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erreur interne du moteur de triage: {exc}") from exc
