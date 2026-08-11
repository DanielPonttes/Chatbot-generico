"""
Testes da camada de API pública: API key, rate limit, versionamento /v1,
CORS e tratamento global de erros.
"""

import json
import time
from collections import deque
from datetime import datetime, timezone
from unittest.mock import AsyncMock

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
from app.models.schemas import NodeMetricsResponse, ProactiveChatRequest
from app.services.notification_mission_catalog import _load_catalog, get_notification_missions
from app.services.persona_service import ProactiveMessageResult


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


def test_admin_status_requires_admin_key_and_returns_sanitized_runtime(
    client,
    monkeypatch,
    patched_services,
):
    monkeypatch.setattr(settings, "api_key", "publica")
    monkeypatch.setattr(settings, "admin_api_key", "admin-secreta")
    monkeypatch.setattr(
        routes,
        "_probe_external_components",
        lambda: {"database": "connected", "spring_api": "reachable (HTTP 200)"},
    )

    assert client.get("/v1/admin/status").status_code == 401
    assert client.get(
        "/v1/admin/status",
        headers={"X-API-Key": "publica"},
    ).status_code == 403

    response = client.get(
        "/v1/admin/status",
        headers={"X-API-Key": "admin-secreta"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["provider"] == "ollama"
    assert body["provider_available"] is True
    assert body["components"] == {
        "database": "connected",
        "spring_api": "reachable (HTTP 200)",
    }
    assert body["uptime_seconds"] >= 0
    assert body["checked_at"].endswith("+00:00") or body["checked_at"].endswith("Z")
    assert "api_key" not in body
    assert "password" not in body


def test_admin_status_fails_closed_when_admin_key_is_not_configured(
    client,
    monkeypatch,
):
    monkeypatch.setattr(settings, "api_key", "publica")
    monkeypatch.setattr(settings, "admin_api_key", None)

    response = client.get(
        "/v1/admin/status",
        headers={"X-API-Key": "publica"},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "admin_auth_not_configured"


def test_admin_status_without_header_is_unauthorized_in_development(
    client,
    monkeypatch,
):
    monkeypatch.setattr(settings, "api_key", None)
    monkeypatch.setattr(settings, "admin_api_key", "admin-secreta")

    response = client.get("/v1/admin/status")

    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "unauthorized"


def test_admin_status_propagates_degraded_provider(
    client,
    monkeypatch,
    patched_services,
):
    monkeypatch.setattr(settings, "api_key", "publica")
    monkeypatch.setattr(settings, "admin_api_key", "admin-secreta")
    monkeypatch.setattr(routes, "_probe_external_components", lambda: {})
    patched_services["provider"].is_available.return_value = False

    response = client.get(
        "/v1/admin/status",
        headers={"X-API-Key": "admin-secreta"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["provider_available"] is False


def test_public_health_sanitizes_database_identifier(
    client,
    monkeypatch,
    patched_services,
):
    class FakeDatabase:
        def health(self):
            return {"database_name": "procel_analytics"}

    class FakeSpring:
        def get_connection_info(self):
            return {"base_url": "http://spring.test", "timeout_seconds": 1}

    class FakeResponse:
        status_code = 200
        is_success = True

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, _url):
            return FakeResponse()

    monkeypatch.setattr(routes, "get_remote_postgres_catalog_service", lambda: FakeDatabase())
    monkeypatch.setattr(routes, "get_spring_api_catalog_service", lambda: FakeSpring())
    monkeypatch.setattr(routes.httpx, "Client", FakeClient)

    response = client.get("/v1/health")

    assert response.status_code == 200
    components = response.json()["components"]
    assert components["database"] == "connected"
    assert "procel_analytics" not in response.text


def test_admin_status_propagates_probe_failures_without_stack_trace(
    client,
    monkeypatch,
    patched_services,
):
    monkeypatch.setattr(settings, "api_key", "publica")
    monkeypatch.setattr(settings, "admin_api_key", "admin-secreta")
    monkeypatch.setattr(
        routes,
        "_probe_external_components",
        lambda: {"database": "unavailable", "spring_api": "unreachable"},
    )

    response = client.get(
        "/v1/admin/status",
        headers={"X-API-Key": "admin-secreta"},
    )

    assert response.status_code == 200
    assert response.json()["components"] == {
        "database": "unavailable",
        "spring_api": "unreachable",
    }
    assert "traceback" not in response.text.lower()


def test_node_metrics_are_admin_only(client, monkeypatch, patched_services):
    monkeypatch.setattr(settings, "api_key", None)
    monkeypatch.setattr(settings, "admin_api_key", "admin-secreta")
    monkeypatch.setattr(routes, "_probe_external_components", lambda: {})
    node_metrics = NodeMetricsResponse(
        schema_version=1,
        collected_at=datetime.now(timezone.utc),
        age_seconds=2.0,
        fresh=True,
        hostname="rtx-test",
        disk_path="/",
        disk_total_bytes=100,
        disk_used_bytes=10,
        gpu_available=False,
        gpus=[],
        services={"backend": "active"},
    )
    monkeypatch.setattr(routes, "read_node_metrics", lambda: node_metrics)

    admin_response = client.get(
        "/v1/admin/status",
        headers={"X-API-Key": "admin-secreta"},
    )
    public_response = client.get("/v1/health")

    assert admin_response.status_code == 200
    assert admin_response.json()["node_metrics"]["hostname"] == "rtx-test"
    assert "node_metrics" not in public_response.json()


def test_admin_status_returns_null_for_invalid_node_snapshot(
    client,
    monkeypatch,
    patched_services,
    tmp_path,
):
    monkeypatch.setattr(settings, "api_key", None)
    monkeypatch.setattr(settings, "admin_api_key", "admin-secreta")
    monkeypatch.setattr(settings, "node_metrics_path", str(tmp_path / "latest.json"))
    monkeypatch.setattr(routes, "_probe_external_components", lambda: {})
    (tmp_path / "latest.json").write_text('{"schema_version": 999}', encoding="utf-8")

    response = client.get(
        "/v1/admin/status",
        headers={"X-API-Key": "admin-secreta"},
    )

    assert response.status_code == 200
    assert response.json()["node_metrics"] is None


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
    assert "/v1/admin/status" in paths
    assert "/v1/notifications/missions" in paths
    assert "/v1/notifications/missions/{mission_id}" in paths
    assert "/v1/notifications/generate" in paths
    assert "/personas" not in paths
    assert "/health" not in paths


def test_openapi_declares_api_key_security(client):
    schema = client.get("/openapi.json").json()

    assert "APIKeyHeader" in schema["components"]["securitySchemes"]
    assert schema["paths"]["/v1/health"]["get"].get("security") in (None, [])
    assert schema["paths"]["/v1/admin/status"]["get"]["security"] == [
        {"APIKeyHeader": []}
    ]


def test_openapi_describes_notification_catalog_and_mission_context(client):
    schema = client.get("/openapi.json").json()

    catalog_operation = schema["paths"]["/v1/notifications/types"]["get"]
    assert "notifications" in catalog_operation["tags"]
    assert catalog_operation["security"] == [{"APIKeyHeader": []}]

    response_schema = catalog_operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert response_schema["items"]["$ref"].endswith("/NotificationTypeResponse")

    context_schema = schema["components"]["schemas"]["ProactiveChatRequest"]["properties"][
        "notification_context"
    ]
    assert context_schema["x-procel-context-groups"]["indoor_telemetry"]
    assert "xp_reward" in context_schema["x-procel-context-groups"]["user_and_rewards"]
    assert any("room_id" in example for example in context_schema["examples"])

    assert schema["paths"]["/v1/notifications/saved"]["post"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]["$ref"].endswith("/SavedNotificationCreateResponse")

    for path, method in (
        ("/v1/notifications/missions", "get"),
        ("/v1/notifications/missions/{mission_id}", "get"),
        ("/v1/notifications/generate", "post"),
    ):
        assert schema["paths"][path][method]["security"] == [{"APIKeyHeader": []}]

    generate_operation = schema["paths"]["/v1/notifications/generate"]["post"]
    assert generate_operation["requestBody"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("/NotificationGenerateRequest")
    generate_schema = schema["components"]["schemas"]["NotificationGenerateRequest"]
    assert generate_schema["properties"]["use_canonical_context"]["default"] is False
    assert "chave administrativa" in generate_schema["properties"][
        "use_canonical_context"
    ]["description"]
    assert generate_operation["responses"]["409"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("/ErrorResponse")
    assert "conflito canônico" in generate_operation["responses"]["409"]["description"]

    proactive_responses = schema["paths"]["/v1/chat/proactive"]["post"]["responses"]
    for code in ("400", "404"):
        assert proactive_responses[code]["content"]["application/json"]["schema"][
            "$ref"
        ].endswith("/ErrorResponse")


def test_notification_catalog_matches_document_categories(client):
    response = client.get("/v1/notifications/types")

    assert response.status_code == 200
    catalog = {item["id"]: item for item in response.json()}
    assert len(catalog) == 11
    assert catalog["missao_convite"]["category"] == "Desafios e Missões"
    assert catalog["feedback_alerta_consumo"]["subtype"] == "Alerta de Consumo Anômalo"
    assert catalog["conquista_badge"]["required_context_vars"] == [
        "badge_name",
        "badge_description",
        "trigger_action",
    ]


def test_notification_catalog_requires_api_key_when_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "api_key", "chave-teste")

    assert client.get("/v1/notifications/types").status_code == 401
    assert client.get(
        "/v1/notifications/types",
        headers={"X-API-Key": "chave-teste"},
    ).status_code == 200


def test_notification_mission_endpoints_require_api_key_when_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "api_key", "chave-teste")

    assert client.get("/v1/notifications/missions").status_code == 401
    assert client.post(
        "/v1/notifications/generate",
        json={"mission_id": "mudanca_visivel", "persona_id": "motivador"},
    ).status_code == 401

    headers = {"X-API-Key": "chave-teste"}
    assert client.get("/v1/notifications/missions", headers=headers).status_code == 200
    assert client.post(
        "/v1/notifications/generate",
        headers=headers,
        json={"mission_id": "mudanca_visivel", "persona_id": "motivador"},
    ).status_code == 409


def test_notification_mission_catalog_exposes_v3_matrix(client):
    response = client.get("/v1/notifications/missions")

    assert response.status_code == 200
    body = response.json()
    assert body["mission_count"] == 64
    assert body["source_document"] == "MissõesXnotificaçõesV3.docx"
    assert body["missions"][0]["mission_id"] == "ultimo_a_apagar"
    assert body["missions"][0]["template_id"] == "missao_convite"
    assert body["missions"][0]["template_required_context_vars"] == [
        "target_action",
        "target_time_window",
        "reward_description",
    ]
    assert body["missions"][0]["agent_inputs"] == ["user_first_name", "xp_reward"]
    assert sum(item["execution_status"] == "catalog_only" for item in body["missions"]) == 1


def test_notification_mission_templates_exist_in_runtime_catalog():
    runtime_template_ids = {
        notification_type.id for notification_type in routes.PersonaService.get_notification_types()
    }
    mapped_missions = [
        mission
        for mission in get_notification_missions()
        if mission.execution_status == "mapped_template"
    ]

    assert len(mapped_missions) == 63
    assert all(mission.template_id in runtime_template_ids for mission in mapped_missions)


def test_notification_mission_catalog_rejects_unknown_runtime_template(tmp_path):
    catalog_path = tmp_path / "notification_missions.json"
    catalog_path.write_text(
        json.dumps(
            {
                "catalog_version": "test",
                "source_document": "test.docx",
                "mission_count": 1,
                "missions": [
                    {
                        "mission_id": "missao_teste",
                        "name": "Missão de teste",
                        "category": "Teste",
                        "subtype": "Teste",
                        "template_id": "template_inexistente",
                        "execution_status": "mapped_template",
                        "example": "Mensagem de teste",
                        "component_inputs": [],
                        "agent_inputs": [],
                        "context_variables": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"template_id\(s\) de missão sem registro técnico"):
        _load_catalog(catalog_path)


def test_notification_mission_lookup_has_stable_not_found_error(client):
    response = client.get("/v1/notifications/missions/mission-que-nao-existe")

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "mission_not_found"


def test_notification_generation_resolves_mission_template(
    client,
    monkeypatch,
    patched_services,
):
    generated = ProactiveMessageResult(
        message="Atenção: há uma anomalia de consumo na sala.",
        context_summary="Sala sala-204",
        prompt_used="prompt de teste",
    )
    generator = AsyncMock(return_value=generated)
    monkeypatch.setattr(routes.PersonaService, "generate_proactive_message", generator)
    monkeypatch.setattr(routes, "save_notification", lambda _: True)

    response = client.post(
        "/v1/notifications/generate",
        json={
            "mission_id": "sala_vazia_luz_off",
            "persona_id": "motivador",
            "notification_context": {
                "anomaly_window": "últimas 2 horas",
                "measured_consumption_kwh": 8.4,
                "expected_consumption_kwh": 5.2,
                "room_id": "sala-204",
                "potential_wasted_kwh": 3.2,
                "recommended_action": "apagar a iluminação",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["reply"] == generated.message
    assert generator.await_args.kwargs["notification_type_id"] == "feedback_alerta_consumo"


def test_notification_generation_fails_if_candidate_is_not_persisted(
    client,
    monkeypatch,
    patched_services,
):
    generated = ProactiveMessageResult(
        message="Candidata que não deve ser retornada como salva.",
        context_summary=None,
        prompt_used="prompt de teste",
    )
    monkeypatch.setattr(
        routes.PersonaService,
        "generate_proactive_message",
        AsyncMock(return_value=generated),
    )
    monkeypatch.setattr(routes, "save_notification", lambda _: False)

    response = client.post(
        "/v1/notifications/generate",
        json={
            "mission_id": "sala_vazia_luz_off",
            "persona_id": "motivador",
            "notification_context": {
                "anomaly_window": "últimas 2 horas",
                "measured_consumption_kwh": 8.4,
                "expected_consumption_kwh": 5.2,
                "room_id": "sala-demo-204",
                "potential_wasted_kwh": 3.2,
                "recommended_action": "apagar a iluminação",
            },
        },
    )

    assert response.status_code == 500
    assert response.json()["detail"]["error"] == "notification_persistence_failed"


def test_notification_generation_rejects_catalog_only_mission(client):
    response = client.post(
        "/v1/notifications/generate",
        json={
            "mission_id": "mudanca_visivel",
            "persona_id": "motivador",
            "notification_context": {},
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "mission_not_executable"


def test_notification_generation_rejects_mission_template_mismatch(client):
    response = client.post(
        "/v1/notifications/generate",
        json={
            "mission_id": "sala_vazia_luz_off",
            "persona_id": "motivador",
            "notification_type_id": "missao_convite",
            "notification_context": {},
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "mission_template_mismatch"


def test_notification_generation_reports_context_validation_separately(client):
    response = client.post(
        "/v1/notifications/generate",
        json={
            "mission_id": "sala_vazia_luz_off",
            "persona_id": "motivador",
            "notification_context": {},
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "validation_error"
    assert "obrigatórias" in response.json()["detail"]["message"]


def test_notification_context_accepts_document_mission_fields():
    request = ProactiveChatRequest(
        persona_id="motivador",
        notification_type_id="missao_convite",
        notification_context={
            "room_id": "sala-204",
            "user_first_name": "Daniel",
            "target_action": "reduzir o consumo entre 18h e 21h",
            "target_time_window": "hoje, das 18h às 21h",
            "reward_description": "100 EcoCoins",
            "xp_reward": 50,
            "coins_reward": 100,
        },
    )

    assert request.notification_context["room_id"] == "sala-204"
    assert request.notification_context["xp_reward"] == 50


def test_notification_context_key_limit_has_documented_boundary(client):
    accepted = ProactiveChatRequest(
        persona_id="motivador",
        notification_context={f"context_{index}": index for index in range(32)},
    )
    assert len(accepted.notification_context) == 32

    response = client.post(
        "/v1/chat/proactive",
        json={
            "persona_id": "motivador",
            "notification_context": {f"context_{index}": index for index in range(33)},
        },
    )

    assert response.status_code == 422


def test_proactive_notification_reports_context_validation_separately(client):
    response = client.post(
        "/v1/chat/proactive",
        json={
            "persona_id": "motivador",
            "notification_type_id": "feedback_alerta_consumo",
            "notification_context": {},
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "validation_error"
    assert "obrigatórias" in response.json()["detail"]["message"]


def test_proactive_notification_reports_unknown_type_as_not_found(client):
    response = client.post(
        "/v1/chat/proactive",
        json={
            "persona_id": "motivador",
            "notification_type_id": "tipo-que-nao-existe",
            "notification_context": {},
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "notification_type_not_found"


def test_proactive_notification_reports_unknown_persona_as_not_found(client):
    response = client.post(
        "/v1/chat/proactive",
        json={"persona_id": "persona-que-nao-existe"},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "persona_not_found"


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


def test_production_requires_postgres_tls(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "api_key", "publica")
    monkeypatch.setattr(settings, "admin_api_key", "admin-secreta")
    monkeypatch.setattr(settings, "cors_allow_origins", "https://app.example")
    monkeypatch.setattr(settings, "rate_limit_per_minute", 60)
    monkeypatch.setattr(settings, "legacy_routes_enabled", False)
    monkeypatch.setattr(settings, "docs_public", False)
    monkeypatch.setattr(settings, "allow_model_override", False)
    monkeypatch.setattr(settings, "allowed_models", "")
    monkeypatch.setattr(settings, "allowed_hosts", "api.example")
    monkeypatch.setattr(settings, "trusted_proxy_networks", "127.0.0.1")
    monkeypatch.setattr(settings, "canonical_context_source", "postgresql")
    monkeypatch.setattr(settings, "remote_pg_sslmode", "disable")

    with pytest.raises(RuntimeError, match="REMOTE_PG_SSLMODE=require"):
        validate_runtime_security()


def test_production_snapshot_mode_rejects_postgres_password_in_backend(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "api_key", "publica")
    monkeypatch.setattr(settings, "admin_api_key", "admin-secreta")
    monkeypatch.setattr(settings, "cors_allow_origins", "https://app.example")
    monkeypatch.setattr(settings, "rate_limit_per_minute", 60)
    monkeypatch.setattr(settings, "legacy_routes_enabled", False)
    monkeypatch.setattr(settings, "docs_public", False)
    monkeypatch.setattr(settings, "allow_model_override", False)
    monkeypatch.setattr(settings, "allowed_models", "")
    monkeypatch.setattr(settings, "allowed_hosts", "api.example")
    monkeypatch.setattr(settings, "trusted_proxy_networks", "127.0.0.1")
    monkeypatch.setattr(settings, "canonical_context_source", "snapshot")
    monkeypatch.setattr(settings, "remote_pg_password", "não-deve-entrar-no-backend")

    with pytest.raises(RuntimeError, match="REMOTE_PG_PASSWORD ausente"):
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
