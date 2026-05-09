from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.core.config import get_settings
from app.models.schemas import HealthResponse
from app.routes.triage import router as triage_router
from app.services.triage_service import engine_status, load_kb_once

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="API professionnelle de triage AlloDocteur. Orientation médicale, pas diagnostic.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(triage_router)


@app.on_event("startup")
def startup() -> None:
    load_kb_once()


@app.exception_handler(ValidationError)
def validation_exception_handler(request: Request, exc: ValidationError):
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {"service": settings.app_name, "version": settings.app_version, "status": "running"}


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    st = engine_status()
    ok = bool(st["engine_loaded"] and st["kb_loaded"])
    return HealthResponse(
        status="ok" if ok else "degraded",
        version=settings.app_version,
        engine_loaded=bool(st["engine_loaded"]),
        kb_loaded=bool(st["kb_loaded"]),
        kb_path=st.get("kb_path"),
    )
