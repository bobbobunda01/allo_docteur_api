from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from app.settings import settings

class AuditLogger:
    def __init__(self):
        self.directory = Path(settings.audit_dir)
        self.directory.mkdir(parents=True, exist_ok=True)

    def write(self, intake, decision) -> str:
        audit_id = f'audit-{uuid4().hex}'
        record = {
            'audit_id': audit_id,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'complaint_sha256': hashlib.sha256(intake.complaint_text.encode('utf-8')).hexdigest(),
            'patient_profile': intake.patient.model_dump(mode='json'),
            'severity_answers': intake.severity_answers,
            'decision': decision.model_dump(mode='json', exclude={'audit_id'}),
        }
        target = self.directory / f"{datetime.now(timezone.utc).date().isoformat()}.jsonl"
        with target.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + '\n')
        return audit_id
