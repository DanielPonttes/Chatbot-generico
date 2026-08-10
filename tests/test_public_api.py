"""
Testes da camada de API pública: API key, rate limit, versionamento /v1,
CORS e tratamento global de erros.
"""

import time
from collections import deque

import pytest

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.requests import Request

from app.api import routes
from app.core.config import settings
from app.core.security import (
    RateLimitMiddleware,
    RequestBodySizeLimitMiddleware,
    _request_client_ip,
    validate_runtime_security,
)
from app.main import _parse_allowed_hosts, _parse_cors_origins
from app.models.schemas import ProactiveChatRequest


# ---------------------------------------------------------------------------
# Autenticação por API key
# ---------------------------------------------------------------------------


def test_api_key_not_required_when_unset(client):
    """Sem API_KEY configurada, a API fica aberta (modo desenvolvimento)."""
    assert client.get("/personas").status_code == 200
    assert client.get("/v1/personas").status_code == 200


def test_api_key_required_when_configured(client, monkeypatch):
    """Com API_KEY configurada, endpoints exigem o header X-API-Key."""
    monkeypatch.setattr(settings, "api_key", "chave-teste")

    sem_chave = client.get("/personas")
    assert sem_chave.status_code == 401
    assert sem_chave.json()["detail"]["error"] == "unauthorized"

    chave_errada = client.get("/personas", headers={"X-API-Key": "errada"})
    assert chave_errada.status_code == 401

    ok = client.get("/personas", headers={"X-API-Key": "chave-teste"})
    assert ok.status_code == 200

    ok_v1 = client.get("/v1/personas", headers={"X-API-Key": "chave-teste"})
    assert ok_v1.status_code == 200


def test_admin_key_is_required_for_destructive_operations(client, monkeypatch):
    monkeypatch.setattr(settings, "api_key", "publica")
    monkeypatch.setattr(settings, "admin_api_key", "admin-secreta")
    monkeypatch.setattr(routes, "clear_all_notifications", lambda: 0)

    assert client.delete(
        "/v1/notifications/saved/all",
        headers={"X-API-Key": "publica"},
    ).status_code == 403

    response = client.delete(
        "/v1/notifications/saved/all",
        headers={"X-API-Key": "admin-secreta"},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "success", "deleted": 0}


def test_health_stays_public_with_api_key(client, monkeypatch, patched_services):
    """Health continua público para monitoramento mesmo com API_KEY ativa."""
    monkeypatch.setattr(settings, "api_key", "chave-teste")

    assert client.get("/health").status_code == 200
    assert client.get("/v1/health").status_code == 200


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


def test_rate_limit_returns_429_when_exceeded(monkeypatch):
    """Após estourar o limite por IP, a API responde 429 com envelope padrão."""
    monkeypatch.setattr(settings, "rate_limit_per_minute", 2)

    mini_app = FastAPI()
    mini_app.add_middleware(RateLimitMiddleware)

    @mini_app.get("/ping")
    def ping():
        return {"pong": True}

    mini_client = TestClient(mini_app)

    assert mini_client.get("/ping").status_code == 200
    assert mini_client.get("/ping").status_code == 200

    terceira = mini_client.get("/ping")
    assert terceira.status_code == 429
    assert terceira.json()["detail"]["error"] == "rate_limit_exceeded"
    assert terceira.headers["Retry-After"] == "60"


def test_rate_limit_disabled_by_default(client):
    """Com limite 0 (padrão), requisições em sequência não são bloqueadas."""
    for _ in range(5):
        assert client.get("/personas").status_code == 200


def test_rate_limit_does_not_trust_forwarded_ip_from_untrusted_peer(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_per_minute", 1)

    mini_app = FastAPI()
    mini_app.add_middleware(RateLimitMiddleware)

    @mini_app.get("/ping")
    def ping():
        return {"pong": True}

    mini_client = TestClient(mini_app)
    assert mini_client.get(
        "/ping", headers={"X-Forwarded-For": "203.0.113.10"}
    ).status_code == 200
    assert mini_client.get(
        "/ping", headers={"X-Forwarded-For": "203.0.113.11"}
    ).status_code == 429


def test_rate_limit_preserves_cors_headers_on_429(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_per_minute", 1)

    mini_app = FastAPI()
    mini_app.add_middleware(RateLimitMiddleware)
    mini_app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://app.example"],
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["X-API-Key"],
    )

    @mini_app.get("/ping")
    def ping():
        return {"pong": True}

    mini_client = TestClient(mini_app)
    headers = {"Origin": "https://app.example"}
    assert mini_client.get("/ping", headers=headers).status_code == 200

    limited = mini_client.get("/ping", headers=headers)
    assert limited.status_code == 429
    assert limited.headers["Access-Control-Allow-Origin"] == "https://app.example"


def test_options_preflight_does_not_consume_rate_limit(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_per_minute", 1)

    mini_app = FastAPI()
    mini_app.add_middleware(RateLimitMiddleware)

    @mini_app.api_route("/ping", methods=["GET", "OPTIONS"])
    def ping():
        return {"pong": True}

    mini_client = TestClient(mini_app)
    assert mini_client.options("/ping").status_code == 200
    assert mini_client.get("/ping").status_code == 200
    assert mini_client.get("/ping").status_code == 429


def test_public_health_and_openapi_do_not_consume_rate_limit(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_per_minute", 1)

    mini_app = FastAPI()
    mini_app.add_middleware(RateLimitMiddleware)

    @mini_app.get("/v1/health")
    def health_probe():
        return {"status": "healthy"}

    @mini_app.post("/v1/chat")
    def chat_probe():
        return {"ok": True}

    mini_client = TestClient(mini_app)
    assert mini_client.get("/v1/health").status_code == 200
    assert mini_client.get("/v1/health").status_code == 200
    assert mini_client.post("/v1/chat").status_code == 200


def test_request_body_limit_returns_413_before_route_processing():
    mini_app = FastAPI()
    mini_app.add_middleware(RequestBodySizeLimitMiddleware, max_body_bytes=8)

    @mini_app.post("/echo")
    def echo(payload: dict):
        return payload

    response = TestClient(mini_app).post("/echo", json={"payload": "too large"})

    assert response.status_code == 413
    assert response.json()["detail"]["error"] == "request_body_too_large"


def test_forwarded_ip_is_used_only_for_a_trusted_proxy(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_networks", "127.0.0.1")

    def request_from(peer, headers):
        return Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": [(key.lower().encode(), value.encode()) for key, value in headers.items()],
                "client": (peer, 443),
                "server": ("api", 8000),
                "scheme": "http",
                "query_string": b"",
                "root_path": "",
                "http_version": "1.1",
            }
        )

    assert _request_client_ip(
        request_from("127.0.0.1", {"CF-Connecting-IP": "203.0.113.10"})
    ) == "203.0.113.10"
    assert _request_client_ip(
        request_from("127.0.0.1", {"X-Forwarded-For": "198.51.100.2, 203.0.113.11"})
    ) == "203.0.113.11"
    assert _request_client_ip(
        request_from("198.51.100.2", {"X-Forwarded-For": "203.0.113.12"})
    ) == "198.51.100.2"


def test_rate_limit_purges_expired_ip_keys(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_per_minute", 1)

    mini_app = FastAPI()
    mini_app.add_middleware(RateLimitMiddleware)

    @mini_app.get("/ping")
    def ping():
        return {"pong": True}

    mini_client = TestClient(mini_app)
    assert mini_client.get("/ping").status_code == 200

    rate_limiter = mini_app.middleware_stack.app
    rate_limiter._hits["198.51.100.1"] = deque([time.monotonic() - 120])
    rate_limiter._last_cleanup = 0.0

    assert mini_client.get("/ping").status_code == 429
    assert "198.51.100.1" not in rate_limiter._hits


# ---------------------------------------------------------------------------
# Versionamento /v1
# ---------------------------------------------------------------------------


def test_v1_routes_available(client, patched_services):
    assert client.get("/v1/health").status_code == 200
    assert client.get("/v1/personas").status_code == 200


def test_openapi_exposes_only_v1_paths(client):
    """O contrato público no OpenAPI deve mostrar apenas os caminhos /v1."""
    paths = client.get("/openapi.json").json()["paths"]
    assert "/v1/personas" in paths
    assert "/v1/health" in paths
    assert "/personas" not in paths
    assert "/health" not in paths


def test_openapi_declares_api_key_security(client):
    schema = client.get("/openapi.json").json()

    assert "APIKeyHeader" in schema["components"]["securitySchemes"]


def test_openapi_remains_public_when_interactive_docs_are_private(client, monkeypatch):
    monkeypatch.setattr(settings, "api_key", "chave-teste")
    monkeypatch.setattr(settings, "docs_public", False)

    assert client.get("/openapi.json").status_code == 200


def test_docs_can_be_protected(client, monkeypatch):
    monkeypatch.setattr(settings, "api_key", "chave-teste")
    monkeypatch.setattr(settings, "docs_public", False)
    monkeypatch.setattr(settings, "legacy_routes_enabled", False)

    assert client.get("/docs").status_code == 401
    assert client.get("/docs", headers={"X-API-Key": "chave-teste"}).status_code == 200


def test_static_test_pages_can_be_protected(client, monkeypatch):
    monkeypatch.setattr(settings, "api_key", "chave-teste")
    monkeypatch.setattr(settings, "legacy_routes_enabled", False)

    for path in ("/", "/notifications", "/rag"):
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"X-API-Key": "chave-teste"}).status_code == 200


def test_legacy_routes_still_work_for_compatibility(client):
    """Caminhos legados sem prefixo continuam respondendo (back-compat)."""
    assert client.get("/personas").status_code == 200


def test_legacy_routes_can_be_disabled(client, monkeypatch):
    """Produção pode encerrar os caminhos sem versionamento."""
    monkeypatch.setattr(settings, "legacy_routes_enabled", False)

    response = client.get("/personas")

    assert response.status_code == 410
    assert response.json()["detail"]["error"] == "legacy_route_disabled"


def test_security_headers_are_present(client):
    response = client.get("/v1/personas")

    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Cache-Control"] == "no-store"


def test_untrusted_host_is_rejected(client):
    response = client.get("/v1/personas", headers={"host": "malicious.example"})

    assert response.status_code == 400


def test_model_override_can_be_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "allow_model_override", False)

    response = client.post(
        "/v1/chat",
        json={
            "session_id": "sessao-teste",
            "message": "Olá",
            "model_override": "gemma4:26b",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "model_override_disabled"


def test_model_override_must_be_in_allowlist(client, monkeypatch):
    monkeypatch.setattr(settings, "allow_model_override", True)
    monkeypatch.setattr(settings, "allowed_models", "gemma4:26b")

    response = client.post(
        "/v1/chat",
        json={
            "session_id": "sessao-teste",
            "message": "Olá",
            "model_override": "outro-modelo:latest",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "model_not_allowed"


def test_model_override_from_allowlist_is_forwarded(client, monkeypatch, patched_services):
    monkeypatch.setattr(settings, "allow_model_override", True)
    monkeypatch.setattr(settings, "allowed_models", "gemma4:26b")

    response = client.post(
        "/v1/chat",
        json={
            "session_id": "sessao-teste",
            "message": "Olá",
            "model_override": "gemma4:26b",
        },
    )

    assert response.status_code == 200
    assert response.json()["model"] == "gemma4:26b"
    patched_services["provider"].generate.assert_awaited_once()
    assert patched_services["provider"].generate.call_args.kwargs["model_override"] == "gemma4:26b"


def test_model_override_rejects_control_characters(client):
    response = client.post(
        "/v1/chat",
        json={
            "session_id": "sessao-teste",
            "message": "Olá",
            "model_override": "gemma4:26b; rm -rf /",
        },
    )

    assert response.status_code == 422


def test_public_notification_creation_cannot_set_reviewed_status(client, monkeypatch):
    monkeypatch.setattr(settings, "api_key", "publica")
    monkeypatch.setattr(settings, "admin_api_key", "admin-secreta")

    response = client.post(
        "/v1/notifications/saved",
        headers={"X-API-Key": "publica"},
        json={
            "type": "Aprovada",
            "content": "Texto",
            "persona": "motivador",
            "model": "gemma4:26b",
        },
    )

    assert response.status_code == 422


def test_saved_notification_error_uses_structured_envelope(client, monkeypatch):
    monkeypatch.setattr(routes, "save_notification", lambda _: False)

    response = client.post(
        "/v1/notifications/saved",
        json={
            "type": "Pendente",
            "content": "Texto",
            "persona": "motivador",
            "model": "gemma4:26b",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "notification_save_failed"
    assert "message" in response.json()["detail"]


def test_production_security_validation_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "api_key", None)
    monkeypatch.setattr(settings, "cors_allow_origins", "*")
    monkeypatch.setattr(settings, "rate_limit_per_minute", 0)
    monkeypatch.setattr(settings, "legacy_routes_enabled", True)
    monkeypatch.setattr(settings, "allow_model_override", True)
    monkeypatch.setattr(settings, "allowed_models", "")
    monkeypatch.setattr(settings, "allowed_hosts", "*")
    monkeypatch.setattr(settings, "docs_public", True)

    with pytest.raises(RuntimeError, match="Configuração insegura"):
        validate_runtime_security()


@pytest.mark.parametrize(
    ("cors_origins", "allowed_hosts"),
    [
        ("https://app.example, *", "api.example"),
        ("", "api.example"),
        ("https://app.example", ""),
    ],
)
def test_production_rejects_empty_or_wildcard_network_policies(
    monkeypatch,
    cors_origins,
    allowed_hosts,
):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "api_key", "chave-teste")
    monkeypatch.setattr(settings, "cors_allow_origins", cors_origins)
    monkeypatch.setattr(settings, "rate_limit_per_minute", 60)
    monkeypatch.setattr(settings, "legacy_routes_enabled", False)
    monkeypatch.setattr(settings, "docs_public", False)
    monkeypatch.setattr(settings, "allow_model_override", False)
    monkeypatch.setattr(settings, "allowed_models", "")
    monkeypatch.setattr(settings, "allowed_hosts", allowed_hosts)

    with pytest.raises(RuntimeError, match="Configuração insegura"):
        validate_runtime_security()


def test_production_rejects_shared_public_and_admin_keys(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "api_key", "same-key")
    monkeypatch.setattr(settings, "admin_api_key", "same-key")
    monkeypatch.setattr(settings, "cors_allow_origins", "https://app.example")
    monkeypatch.setattr(settings, "rate_limit_per_minute", 60)
    monkeypatch.setattr(settings, "legacy_routes_enabled", False)
    monkeypatch.setattr(settings, "docs_public", False)
    monkeypatch.setattr(settings, "allow_model_override", False)
    monkeypatch.setattr(settings, "allowed_models", "")
    monkeypatch.setattr(settings, "allowed_hosts", "api.example")
    monkeypatch.setattr(settings, "trusted_proxy_networks", "127.0.0.1")

    with pytest.raises(RuntimeError, match="distintos"):
        validate_runtime_security()


def test_production_rejects_overly_broad_proxy_network(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "api_key", "publica")
    monkeypatch.setattr(settings, "admin_api_key", "admin-secreta")
    monkeypatch.setattr(settings, "cors_allow_origins", "https://app.example")
    monkeypatch.setattr(settings, "rate_limit_per_minute", 60)
    monkeypatch.setattr(settings, "legacy_routes_enabled", False)
    monkeypatch.setattr(settings, "docs_public", False)
    monkeypatch.setattr(settings, "allow_model_override", False)
    monkeypatch.setattr(settings, "allowed_hosts", "api.example")
    monkeypatch.setattr(settings, "trusted_proxy_networks", "0.0.0.0/0")

    with pytest.raises(RuntimeError, match="amplo demais"):
        validate_runtime_security()


def test_notification_context_rejects_large_serialized_payload(client):
    response = client.post(
        "/v1/chat/proactive",
        json={
            "persona_id": "motivador",
            "notification_context": {"details": "x" * 9_000},
        },
    )

    assert response.status_code == 422


def test_notification_context_rejects_non_json_values():
    with pytest.raises(ValidationError, match="apenas valores JSON"):
        ProactiveChatRequest(
            persona_id="motivador",
            notification_context={"details": object()},
        )


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------


def test_parse_cors_origins():
    assert _parse_cors_origins("*") == ["*"]
    assert _parse_cors_origins("") == ["*"]
    assert _parse_cors_origins("https://a.com, https://b.com ") == [
        "https://a.com",
        "https://b.com",
    ]


def test_parse_allowed_hosts_does_not_turn_empty_value_into_wildcard():
    assert _parse_allowed_hosts("") == []
    assert _parse_allowed_hosts("api.example, admin.example") == [
        "api.example",
        "admin.example",
    ]


# ---------------------------------------------------------------------------
# Tratamento global de erros
# ---------------------------------------------------------------------------


def test_global_exception_handler_returns_consistent_envelope(monkeypatch):
    """Erros inesperados viram 500 no mesmo envelope dos erros de negócio."""
    from app.main import app

    def boom():
        raise RuntimeError("falha inesperada")

    monkeypatch.setattr(routes.PersonaService, "get_personas", boom)

    # raise_server_exceptions=False simula o comportamento over-the-wire:
    # em produção, o cliente HTTP recebe o 500 padronizado do handler global.
    wire_client = TestClient(app, raise_server_exceptions=False)
    response = wire_client.get("/personas")

    assert response.status_code == 500
    body = response.json()
    assert body["detail"]["error"] == "internal_error"
