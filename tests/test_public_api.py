"""
Testes da camada de API pública: API key, rate limit, versionamento /v1,
CORS e tratamento global de erros.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes
from app.core.config import settings
from app.core.security import RateLimitMiddleware
from app.main import _parse_cors_origins


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


def test_legacy_routes_still_work_for_compatibility(client):
    """Caminhos legados sem prefixo continuam respondendo (back-compat)."""
    assert client.get("/personas").status_code == 200


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
