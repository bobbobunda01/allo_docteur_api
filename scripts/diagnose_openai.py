from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.settings import BASE_DIR, settings

try:
    import httpx
    from openai import OpenAI
except ImportError as exc:
    print(f'Dépendance absente: {exc}')
    raise SystemExit(10)


def mask(value: str) -> str:
    if not value:
        return 'ABSENTE'
    return f'{value[:7]}...{value[-4:]}' if len(value) > 12 else '***'


def main() -> int:
    print('=' * 72)
    print('DIAGNOSTIC OPENAI — ALLODOCTEUR V6')
    print('=' * 72)
    print('Projet       :', BASE_DIR)
    print('.env présent :', (BASE_DIR / '.env').exists())
    print('Clé          :', mask(settings.openai_api_key))
    print('Modèle       :', settings.openai_model)
    print('LLM activé   :', settings.allodocteur_llm_enabled)
    if not settings.openai_api_key:
        print('ÉCHEC: OPENAI_API_KEY absente.')
        return 1

    timeout = httpx.Timeout(
        connect=settings.openai_connect_timeout_seconds,
        read=settings.openai_read_timeout_seconds,
        write=settings.openai_write_timeout_seconds,
        pool=settings.openai_pool_timeout_seconds,
    )
    client = OpenAI(
        api_key=settings.openai_api_key,
        timeout=timeout,
        max_retries=0,
    )
    started = time.perf_counter()
    try:
        response = client.responses.create(
            model=settings.openai_model,
            input='Réponds uniquement par OK.',
            max_output_tokens=20,
        )
        elapsed = time.perf_counter() - started
        print('Authentification : OK')
        print('Responses API    : OK')
        print('Réponse          :', response.output_text)
        print('Response ID      :', response.id)
        print('Durée            :', round(elapsed, 3), 's')
        return 0
    except Exception as exc:
        elapsed = time.perf_counter() - started
        print('ERREUR TYPE      :', type(exc).__name__)
        print('ERREUR MESSAGE   :', str(exc))
        print('Durée            :', round(elapsed, 3), 's')
        print(json.dumps({'error': type(exc).__name__, 'message': str(exc)}, ensure_ascii=False, indent=2))
        return 2


if __name__ == '__main__':
    sys.exit(main())
