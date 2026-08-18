from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes_triage import router
from app.logging_config import configure_logging
from app.settings import settings

configure_logging()
logger = logging.getLogger('allodocteur')

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url='/docs' if settings.environment != 'production' else None,
    redoc_url='/redoc' if settings.environment != 'production' else None,
)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=['GET', 'POST'],
        allow_headers=['Content-Type', 'X-Admin-Token', 'X-Request-ID'],
    )


@app.middleware('http')
async def request_context(request: Request, call_next):
    request_id = request.headers.get('X-Request-ID') or uuid.uuid4().hex
    try:
        response = await call_next(request)
    except Exception:
        logger.exception('Unhandled request error request_id=%s', request_id)
        return JSONResponse(status_code=500, content={'detail': 'Erreur interne.', 'request_id': request_id})
    response.headers['X-Request-ID'] = request_id
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response


app.include_router(router)
