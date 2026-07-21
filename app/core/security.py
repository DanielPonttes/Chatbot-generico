"""
Segurança da API pública: autenticação por API key e rate limiting.

Ambos são opcionais e controlados por variáveis de ambiente:
- API_KEY: se definida, exige o header X-API-Key em todos os endpoints
  (exceto health/docs, que permanecem públicos para monitoramento).
- RATE_LIMIT_PER_MINUTE: se maior que 0, limita requisições por IP.
"""

import logging
import secrets
import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings

logger = logging.getLogger(__name__)

API_KEY_HEADER_NAME = "X-API-Key"

_api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False)

# Caminhos que permanecem públicos mesmo com API_KEY configurada
# (monitoramento e documentação interativa).
PUBLIC_PATHS = {
    "/health",
    "/v1/health",
    "/docs",
    "/redoc",
    "/openapi.json",
}


async def verify_api_key(
    request: Request,
    api_key: str | None = Depends(_api_key_header),
) -> None:
    """
    Dependência de autenticação da API.

    - Sem API_KEY configurada: libera tudo (modo desenvolvimento).
    - Com API_KEY configurada: exige header X-API-Key válido,
      exceto nos caminhos públicos (health e docs).
    """
    if not settings.api_key:
        return

    if request.url.path in PUBLIC_PATHS:
        return

    if api_key and secrets.compare_digest(api_key, settings.api_key):
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "error": "unauthorized",
            "message": f"Header {API_KEY_HEADER_NAME} ausente ou inválido.",
        },
    )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limit em memória por IP (janela deslizante de 1 minuto).

    Ativado apenas quando settings.rate_limit_per_minute > 0.
    Observação: o contador é por processo — em deploy multi-worker,
    cada worker mantém seu próprio contador.
    """

    def __init__(self, app) -> None:
        super().__init__(app)
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    async def dispatch(self, request: Request, call_next):
        limit = settings.rate_limit_per_minute
        if limit <= 0:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        window_start = now - 60.0

        with self._lock:
            hits = self._hits[client_ip]
            while hits and hits[0] < window_start:
                hits.popleft()

            if len(hits) >= limit:
                logger.warning("Rate limit excedido para %s em %s", client_ip, request.url.path)
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "detail": {
                            "error": "rate_limit_exceeded",
                            "message": f"Limite de {limit} requisições por minuto excedido.",
                        }
                    },
                    headers={"Retry-After": "60"},
                )

            hits.append(now)

        return await call_next(request)
