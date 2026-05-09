from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends

from app.core.security import verify_api_key
from app.models.schemas import TriagePayload, TriageResponse
from app.services.triage_service import DISCLAIMER, run_triage
from app.utils.logging_utils import anonymize_text, append_jsonl

router = APIRouter(prefix="", tags=["triage"])


@router.post("/triage", response_model=TriageResponse, dependencies=[Depends(verify_api_key)])
def triage(payload: TriagePayload) -> TriageResponse:
    request_id = str(uuid.uuid4())
    t0 = time.perf_counter()
    engine_payload = payload.to_engine_payload()
    result: dict[str, Any] = run_triage(engine_payload, dynamic_answers=payload.dynamic_answers)
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

    append_jsonl({
        "request_id": request_id,
        "event": "triage.completed",
        "elapsed_ms": elapsed_ms,
        "complaint_hash": anonymize_text(payload.complaint_text),
        "complaint_len": len(payload.complaint_text or ""),
        "priority_code": result.get("priority_code"),
        "province": payload.province,
        "sex": payload.sex,
    })

    return TriageResponse(
        request_id=request_id,
        priority_code=result.get("priority_code", "P4"),
        color=result.get("color"),
        urgency_label=result.get("urgency_label"),
        orientation=result.get("orientation"),
        message=result.get("message"),
        reasons=result.get("reasons") or [],
        activated_domains=result.get("activated_domains") or [],
        activated_entries=result.get("activated_entries") or [],
        activated_modifiers=result.get("activated_modifiers") or [],
        activated_patterns=result.get("activated_patterns") or [],
        score_total=result.get("score_total"),
        score_breakdown=result.get("score_breakdown") or [],
        normalized_profile=result.get("normalized_profile") or {},
        case_fields=result.get("case_fields") or {},
        asked_questions=result.get("asked_questions") or [],
        disclaimer=DISCLAIMER,
    )
