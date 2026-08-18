from fastapi import APIRouter, Header, HTTPException, status

from api.schemas import InternalTriageResponse, TriageRequest, TriageResponse
from app.settings import settings
from services.triage_service import TriageService

router = APIRouter(prefix='/v1', tags=['triage'])
service = TriageService()


@router.get('/health')
def health():
    return {
        'status': 'ok',
        'version': settings.app_version,
        'llm_enabled': settings.allodocteur_llm_enabled,
        'kb_used': False,
        'follow_up_questions': False,
        'severity_signs': 17,
    }


@router.post('/triage', response_model=TriageResponse)
def triage(payload: TriageRequest):
    return service.triage_public(payload)


@router.post('/triage/internal', response_model=InternalTriageResponse)
def triage_internal(payload: TriageRequest, x_admin_token: str | None = Header(default=None)):
    if not settings.admin_api_token or x_admin_token != settings.admin_api_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Accès interne refusé.',
        )
    return service.triage(payload)
