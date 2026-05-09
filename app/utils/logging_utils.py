from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import get_settings


def anonymize_text(text: str) -> str:
    """Ne stocke pas le texte patient en clair : hash + longueur uniquement."""
    text = text or ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def append_jsonl(event: dict[str, Any]) -> None:
    settings = get_settings()
    if not settings.enable_request_logs:
        return
    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    event["ts"] = datetime.now(timezone.utc).isoformat()
    with (log_dir / "triage_api_events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
