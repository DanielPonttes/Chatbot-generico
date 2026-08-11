"""
Segurança da API pública: autenticação por API key e rate limiting.

Ambos são opcionais e controlados por variáveis de ambiente:
- API_KEY: se definida, exige o header X-API-Key em todos os endpoints
  (exceto health/OpenAPI, que permanecem públicos para monitoramento e contrato).
- RATE_LIMIT_PER_MINUTE: se maior que 0, limita requisições por IP.
"""

import logging
import secrets
import time
from collections import defaultdict, deque
from functools import lru_cache
from ipaddress import ip_address, ip_network
from threading import Lock
from typing import Final

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings

logger = logging.getLogger(__name__)

API_KEY_HEADER_NAME = "X-API-Key"

_api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False)

PUBLIC_PATHS: Final = {
    "/health",
    "/v1/health",
    "/openapi.json",
}

DOCS_PATHS: Final = {"/docs", "/redoc"}
STATIC_PATHS: Final = {"/", "/notifications", "/rag"}


def _csv_values(value: str) -> set[str]:
    """Normaliza uma configuração CSV sem transformar vazio em wildcard."""
    return {item.strip() for item in value.split(",") if item.strip()}


@lru_cache(maxsize=16)
def _parsed_trusted_proxy_networks(value: str) -> tuple:
    """Faz o parse da configuração de proxy uma vez por valor configurado."""
    networks = []
    for item in _csv_values(value):
        try:
            networks.append(ip_network(item, strict=False))
        except ValueError:
            logger.warning("Rede de proxy confiável inválida: %s", item)
    return tuple(networks)


def _trusted_proxy(peer_host: str | None) -> bool:
    """Aceita headers de proxy somente de IPs/redes explicitamente confiáveis."""
    if not peer_host:
        return False

    try:
        peer = ip_address(peer_host)
    except ValueError:
        return False

    for network in _parsed_trusted_proxy_networks(settings.trusted_proxy_networks):
        if peer in network:
            return True
    return False


def _request_client_ip(request: Request) -> str:
    """Obtém o IP de origem sem aceitar XFF arbitrário de clientes diretos."""
    peer_host = request.client.host if request.client else None
    if not _trusted_proxy(peer_host):
        return peer_host or "unknown"

    for header_name in ("cf-connecting-ip", "x-forwarded-for"):
        value = request.headers.get(header_name)
        if not value:
            continue
        # Proxies confiáveis devem sobrescrever/anexar o IP real; no XFF,
        # use o salto mais próximo da aplicação para não aceitar um prefixo
        # injetado pelo cliente. Em Cloudflare, CF-Connecting-IP tem prioridade.
        candidate = value.rsplit(",", 1)[-1].strip()
        try:
            ip_address(candidate)
        except ValueError:
            continue
        return candidate

    return peer_host or "unknown"


def _constant_time_key_match(candidate: str | None, expected: str | None) -> bool:
    """Compara chaves sem transformar entrada malformada em erro 500."""
    if not candidate or not expected:
        return False
    try:
        return secrets.compare_digest(candidate, expected)
    except (TypeError, ValueError):
        return False


async def verify_api_key(
    request: Request,
    api_key: str | None = Depends(_api_key_header),
) -> None:
    """
    Dependência de autenticação da API.

    - Sem API_KEY configurada: libera somente em desenvolvimento/teste.
    - Em produção, configuração ausente falha fechado com 503.
    - Com API_KEY configurada: exige header X-API-Key válido,
      exceto nos caminhos públicos de monitoramento e OpenAPI.
    """
    path = request.url.path

    if request.method == "OPTIONS":
        return

    is_interactive_docs = path in DOCS_PATHS
    is_static_page = path in STATIC_PATHS
    if path in PUBLIC_PATHS or (settings.docs_public and is_interactive_docs):
        return

    if (
        not is_interactive_docs
        and not is_static_page
        and not settings.legacy_routes_enabled
        and not path.startswith("/v1/")
    ):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={
                "error": "legacy_route_disabled",
                "message": "Use a API versionada sob /v1.",
            },
        )

    if not settings.api_key:
        if settings.environment == "production":
            logger.error("API_KEY ausente em ambiente de produção")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": "authentication_not_configured",
                    "message": "A autenticação da API não está configurada.",
                },
            )
        return

    valid_keys = [key for key in (settings.api_key, settings.admin_api_key) if key]
    if any(_constant_time_key_match(api_key, key) for key in valid_keys):
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "error": "unauthorized",
            "message": f"Header {API_KEY_HEADER_NAME} ausente ou inválido.",
        },
    )


async def verify_admin_api_key(
    request: Request,
    api_key: str | None = Depends(_api_key_header),
) -> None:
    """Exige a chave administrativa para mutações sensíveis."""
    if request.method == "OPTIONS":
        return

    if not settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "admin_auth_not_configured",
                "message": "A chave administrativa não está configurada.",
            },
        )

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "unauthorized",
                "message": f"Header {API_KEY_HEADER_NAME} ausente ou inválido.",
            },
        )

    if _constant_time_key_match(api_key, settings.admin_api_key):
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "error": "admin_scope_required",
            "message": "A operação exige a chave administrativa.",
        },
    )


def validate_model_override(model_override: str | None) -> str | None:
    """Valida o modelo solicitado sem permitir seleção arbitrária em produção."""
    if model_override is None:
        return None

    if not settings.allow_model_override:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "model_override_disabled",
                "message": "A seleção de modelo por requisição está desabilitada.",
            },
        )

    allowed = {
        item.strip()
        for item in settings.allowed_models.split(",")
        if item.strip()
    }
    if allowed and model_override not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "model_not_allowed",
                "message": "O modelo solicitado não está na allowlist.",
            },
        )

    if settings.environment == "production" and not allowed:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "model_allowlist_not_configured",
                "message": "A allowlist de modelos não está configurada.",
            },
        )

    return model_override


def validate_runtime_security() -> None:
    """Impede a inicialização de uma configuração pública insegura."""
    if settings.environment != "production":
        return

    problems: list[str] = []
    if not settings.api_key:
        problems.append("API_KEY")
    if not settings.admin_api_key:
        problems.append("ADMIN_API_KEY")
    if settings.api_key and settings.api_key == settings.admin_api_key:
        problems.append("API_KEY e ADMIN_API_KEY distintos")
    cors_origins = _csv_values(settings.cors_allow_origins)
    if not cors_origins or "*" in cors_origins:
        problems.append("CORS_ALLOW_ORIGINS explícito e sem wildcard")
    if settings.rate_limit_per_minute <= 0:
        problems.append("RATE_LIMIT_PER_MINUTE maior que zero")
    if settings.legacy_routes_enabled:
        problems.append("LEGACY_ROUTES_ENABLED=false")
    if settings.docs_public:
        problems.append("DOCS_PUBLIC=false")
    if settings.allow_model_override and not settings.allowed_models.strip():
        problems.append("ALLOWED_MODELS quando ALLOW_MODEL_OVERRIDE=true")
    if settings.remote_pg_sslmode not in {"require", "verify-ca", "verify-full"}:
        problems.append("REMOTE_PG_SSLMODE=require/verify-ca/verify-full")
    allowed_hosts = _csv_values(settings.allowed_hosts)
    if not allowed_hosts or "*" in allowed_hosts:
        problems.append("ALLOWED_HOSTS explícito e não vazio")
    proxy_networks = _parsed_trusted_proxy_networks(settings.trusted_proxy_networks)
    if not proxy_networks or len(proxy_networks) != len(_csv_values(settings.trusted_proxy_networks)):
        problems.append("TRUSTED_PROXY_NETWORKS válido e explícito")
    if any(
        network.prefixlen < (8 if network.version == 4 else 32)
        for network in proxy_networks
    ):
        problems.append("TRUSTED_PROXY_NETWORKS não pode ser amplo demais")

    if problems:
        raise RuntimeError(
            "Configuração insegura para produção; ajuste: " + ", ".join(problems)
        )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adiciona headers mínimos contra cache indevido e interpretação insegura."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=()",
        )

        if request.url.path.startswith("/v1/") or request.url.path in DOCS_PATHS | {"/openapi.json"}:
            response.headers.setdefault("Cache-Control", "no-store")

        trusted_forwarded_proto = (
            _trusted_proxy(request.client.host if request.client else None)
            and request.headers.get("x-forwarded-proto") == "https"
        )
        if request.url.scheme == "https" or trusted_forwarded_proto:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000",
            )

        return response


class _RequestBodyTooLarge(Exception):
    """Sinal interno para interromper a leitura de corpo acima do limite."""


class RequestBodySizeLimitMiddleware:
    """Rejeita corpos HTTP maiores que o limite antes do processamento da rota."""

    def __init__(self, app, max_body_bytes: int = 2 * 1024 * 1024) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or self.max_body_bytes <= 0:
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        raw_content_length = headers.get(b"content-length")
        if raw_content_length:
            try:
                if int(raw_content_length) > self.max_body_bytes:
                    await self._reject(scope, receive, send)
                    return
            except ValueError:
                pass

        received = 0
        response_started = False

        async def tracked_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    raise _RequestBodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, tracked_send)
        except _RequestBodyTooLarge:
            if not response_started:
                await self._reject(scope, receive, send)

    async def _reject(self, scope, receive, send) -> None:
        response = JSONResponse(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            content={
                "detail": {
                    "error": "request_body_too_large",
                    "message": "O corpo da requisição excede o limite permitido.",
                }
            },
        )
        await response(scope, receive, send)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limit em memória por IP (janela deslizante de 1 minuto).

    Ativado apenas quando settings.rate_limit_per_minute > 0.
    Observação: o contador é por processo — em deploy multi-worker,
    cada worker mantém seu próprio contador. Headers de proxy só são usados
    quando o peer pertence a TRUSTED_PROXY_NETWORKS.
    """

    def __init__(self, app) -> None:
        super().__init__(app)
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()
        self._last_cleanup = 0.0

    async def dispatch(self, request: Request, call_next):
        limit = settings.rate_limit_per_minute
        if limit <= 0 or request.method == "OPTIONS" or request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        client_ip = _request_client_ip(request)
        now = time.monotonic()
        window_start = now - 60.0

        with self._lock:
            # Limpeza periódica evita manter uma chave por cada IP que já
            # deixou de fazer requisições, sem varrer a tabela a cada hit.
            if now - self._last_cleanup >= 60.0:
                for key, key_hits in list(self._hits.items()):
                    while key_hits and key_hits[0] < window_start:
                        key_hits.popleft()
                    if not key_hits:
                        del self._hits[key]
                self._last_cleanup = now

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
