"""
Testes para os endpoints de integração externa.
"""

from types import SimpleNamespace

import pytest

from app.api import routes
from app.core.config import settings


class FakeRemoteDatabaseService:
    def health(self):
        return {
            "host": "srv1428963.hstgr.cloud",
            "port": 5432,
            "database": "procel_analytics",
            "user": "postgres",
            "sslmode": "prefer",
            "status": "connected",
            "database_name": "procel_analytics",
            "current_user": "postgres",
        }

    def list_tables(self):
        return [
            {
                "schema": "public",
                "table": "medicao",
                "columns_count": 5,
                "estimated_rows": 61,
                "category": "telemetria",
                "relevance_score": 100,
                "relevance_reason": "Fonte principal de medições.",
                "preview_endpoint": "/integrations/database/tables/public/medicao/rows",
            },
            {
                "schema": "public",
                "table": "sensor",
                "columns_count": 4,
                "estimated_rows": 12,
                "category": "telemetria",
                "relevance_score": 95,
                "relevance_reason": "Relaciona sensores aos compartimentos.",
                "preview_endpoint": "/integrations/database/tables/public/sensor/rows",
            },
        ]

    def describe_table(self, schema_name, table_name):
        assert schema_name == "public"
        assert table_name == "medicao"
        return {
            "schema": "public",
            "table": "medicao",
            "columns_count": 5,
            "estimated_rows": 61,
            "category": "telemetria",
            "relevance_score": 100,
            "relevance_reason": "Fonte principal de medições.",
            "preview_endpoint": "/integrations/database/tables/public/medicao/rows",
            "columns": [
                {
                    "name": "id",
                    "data_type": "uuid",
                    "nullable": False,
                    "is_primary_key": True,
                    "references": None,
                },
                {
                    "name": "sensor_external_id",
                    "data_type": "character varying",
                    "nullable": False,
                    "is_primary_key": False,
                    "references": "public.sensor.external_id",
                },
            ],
        }

    def preview_rows(self, schema_name, table_name, limit, offset):
        assert schema_name == "public"
        assert table_name == "medicao"
        assert limit == 5
        assert offset == 0
        return {
            "schema": "public",
            "table": "medicao",
            "limit": 5,
            "offset": 0,
            "row_count": 1,
            "rows": [
                {
                    "id": "abc",
                    "sensor_external_id": "SII-001",
                    "source": "mock",
                }
            ],
        }

    def search_rooms(self, query_text="", limit=20):
        assert limit == 20
        return [
            {
                "id": "2",
                "label": "Elevador",
                "description": "(ANG) Anglo | Circulacao | Campus Anglo",
                "metadata": {"predio_id": "Campus Anglo|(ANG) Anglo"},
            }
        ]

    def search_sensors(self, query_text="", room_id=None, limit=20):
        assert room_id in (None, "2")
        assert limit == 20
        return [
            {
                "id": "SII-001",
                "label": "SII Smart - Sala 400D",
                "description": "SII Smart - Sala 400D | SII_SMART | Elevador",
                "metadata": {"room_id": "2", "tipo_nome": "SII_SMART"},
            }
        ]

    def search_people(self, query_text="", limit=20):
        assert limit == 20
        return [
            {
                "id": "ravilon",
                "label": "Ravilon A. Santos",
                "description": "MAT-001 | ravilon@exemplo.com",
                "metadata": {},
            }
        ]


class FakeSpringService:
    def get_connection_info(self):
        return {
            "base_url": "http://srv1428963.hstgr.cloud:8080",
            "timeout_seconds": 15.0,
        }

    def list_endpoints(self):
        return [
            {
                "id": "sensor_measurements_latest",
                "category": "medicoes",
                "method": "GET",
                "path_template": "/api/sensors/{sensor_external_id}/medicoes/latest",
                "description": "Última medição do sensor.",
                "discovery_source": "confirmed",
                "relevance_score": 100,
                "relevance_reason": "Ideal para cards de status.",
                "invoke_supported": True,
                "side_effect": False,
                "example_path_params": {"sensor_external_id": "SII-001"},
                "example_query_params": {},
                "example_body": None,
            }
        ]

    def invoke_endpoint(self, endpoint_id, path_params, query_params, body):
        assert endpoint_id == "sensor_measurements_latest"
        assert path_params == {"sensor_external_id": "SII-001"}
        assert query_params == {}
        assert body is None
        return {
            "endpoint_id": endpoint_id,
            "method": "GET",
            "path_template": "/api/sensors/{sensor_external_id}/medicoes/latest",
            "final_url": "http://srv1428963.hstgr.cloud:8080/api/sensors/SII-001/medicoes/latest",
            "status_code": 200,
            "content_type": "application/json",
            "data": {
                "sensorExternalId": "SII-001",
                "source": "mock",
            },
        }


def test_integrations_catalog_returns_combined_sources(client, monkeypatch):
    monkeypatch.setattr(
        routes,
        "get_remote_postgres_catalog_service",
        lambda: FakeRemoteDatabaseService(),
    )
    monkeypatch.setattr(
        routes,
        "get_spring_api_catalog_service",
        lambda: FakeSpringService(),
    )

    response = client.get("/integrations/catalog")

    assert response.status_code == 200
    data = response.json()
    assert data["database"]["connection"]["database"] == "procel_analytics"
    assert data["spring_api"]["connection"]["base_url"] == "http://srv1428963.hstgr.cloud:8080"
    assert data["recommendations"]["database_tables"][0]["table"] == "medicao"


def test_remote_database_table_detail(client, monkeypatch):
    monkeypatch.setattr(
        routes,
        "get_remote_postgres_catalog_service",
        lambda: FakeRemoteDatabaseService(),
    )

    response = client.get("/integrations/database/tables/public/medicao")

    assert response.status_code == 200
    data = response.json()
    assert data["table"] == "medicao"
    assert data["columns"][0]["name"] == "id"
    assert data["columns"][1]["references"] == "public.sensor.external_id"


def test_remote_database_rows_preview(client, monkeypatch):
    monkeypatch.setattr(
        routes,
        "get_remote_postgres_catalog_service",
        lambda: FakeRemoteDatabaseService(),
    )

    response = client.get("/integrations/database/tables/public/medicao/rows?limit=5")

    assert response.status_code == 200
    data = response.json()
    assert data["row_count"] == 1
    assert data["rows"][0]["sensor_external_id"] == "SII-001"


def test_list_spring_endpoints(client, monkeypatch):
    monkeypatch.setattr(
        routes,
        "get_spring_api_catalog_service",
        lambda: FakeSpringService(),
    )

    response = client.get("/integrations/spring/endpoints")

    assert response.status_code == 200
    data = response.json()
    assert data["connection"]["base_url"] == "http://srv1428963.hstgr.cloud:8080"
    assert data["endpoints"][0]["id"] == "sensor_measurements_latest"


def test_lookup_context_rooms(client, monkeypatch):
    monkeypatch.setattr(
        routes,
        "get_remote_postgres_catalog_service",
        lambda: FakeRemoteDatabaseService(),
    )

    response = client.get("/integrations/context/rooms?query=elev")

    assert response.status_code == 200
    data = response.json()
    assert data[0]["id"] == "2"
    assert data[0]["label"] == "Elevador"


def test_lookup_context_sensors(client, monkeypatch):
    monkeypatch.setattr(
        routes,
        "get_remote_postgres_catalog_service",
        lambda: FakeRemoteDatabaseService(),
    )

    response = client.get("/integrations/context/sensors?room_id=2")

    assert response.status_code == 200
    data = response.json()
    assert data[0]["id"] == "SII-001"
    assert data[0]["metadata"]["room_id"] == "2"


def test_lookup_context_people(client, monkeypatch):
    monkeypatch.setattr(
        routes,
        "get_remote_postgres_catalog_service",
        lambda: FakeRemoteDatabaseService(),
    )

    response = client.get("/integrations/context/people?query=ravi")

    assert response.status_code == 200
    data = response.json()
    assert data[0]["id"] == "ravilon"
    assert "MAT-001" in data[0]["description"]


def test_invoke_spring_endpoint(client, monkeypatch):
    monkeypatch.setattr(
        routes,
        "get_spring_api_catalog_service",
        lambda: FakeSpringService(),
    )

    response = client.post(
        "/integrations/spring/endpoints/sensor_measurements_latest/invoke",
        json={"path_params": {"sensor_external_id": "SII-001"}},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status_code"] == 200
    assert data["data"]["sensorExternalId"] == "SII-001"


# ---------------------------------------------------------------------------
# Autenticação JWT da API Spring Boot
# ---------------------------------------------------------------------------


def _make_jwt(expires_in: int = 3600) -> str:
    import base64
    import json as jsonlib
    import time as timelib

    payload = {"sub": "admin", "exp": int(timelib.time()) + expires_in}
    encoded = base64.urlsafe_b64encode(jsonlib.dumps(payload).encode()).decode().rstrip("=")
    return f"header.{encoded}.signature"


class FakeHttpxResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.headers = {"content-type": "application/json"}
        self.request = SimpleNamespace(url="https://procel.test/fake")

    def json(self):
        return self._payload

    @property
    def text(self):
        import json as jsonlib

        return jsonlib.dumps(self._payload)


class FakeHttpxClient:
    """Simula o httpx.Client: login em /api/auth/login e chamadas com Bearer."""

    login_calls: list = []
    api_calls: list = []
    fail_first_with_401: bool = False

    def __init__(self, timeout=None):
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, json=None):
        assert url.endswith("/api/auth/login")
        assert json == {"email": "admin@procel.local", "password": "admin123"}
        FakeHttpxClient.login_calls.append(url)
        return FakeHttpxResponse(200, {"accessToken": _make_jwt(), "tokenType": "Bearer"})

    def request(self, method, url, params=None, json=None, headers=None):
        FakeHttpxClient.api_calls.append({"method": method, "url": url, "headers": headers})
        if FakeHttpxClient.fail_first_with_401 and len(FakeHttpxClient.api_calls) == 1:
            return FakeHttpxResponse(401, {"error": "unauthorized"})
        return FakeHttpxResponse(200, {"sensorExternalId": "SII-002"})


@pytest.fixture
def spring_service_with_auth(monkeypatch):
    from app.services import integration_catalog
    from app.services.integration_catalog import SpringApiCatalogService

    FakeHttpxClient.login_calls = []
    FakeHttpxClient.api_calls = []
    FakeHttpxClient.fail_first_with_401 = False

    monkeypatch.setattr(integration_catalog.httpx, "Client", FakeHttpxClient)
    monkeypatch.setattr(settings, "remote_spring_base_url", "https://procel.test")
    monkeypatch.setattr(settings, "remote_spring_username", "admin@procel.local")
    monkeypatch.setattr(settings, "remote_spring_password", "admin123")

    return SpringApiCatalogService()


def test_spring_invoke_authenticates_and_caches_token(spring_service_with_auth):
    service = spring_service_with_auth

    first = service.invoke_endpoint(
        "sensor_measurements_latest", path_params={"sensor_external_id": "SII-002"}
    )
    second = service.invoke_endpoint(
        "sensor_measurements_latest", path_params={"sensor_external_id": "SII-002"}
    )

    assert first["status_code"] == 200
    assert second["status_code"] == 200
    assert len(FakeHttpxClient.login_calls) == 1
    assert len(FakeHttpxClient.api_calls) == 2
    for call in FakeHttpxClient.api_calls:
        assert call["headers"]["Authorization"].startswith("Bearer ")


def test_spring_invoke_refreshes_token_on_401(spring_service_with_auth):
    FakeHttpxClient.fail_first_with_401 = True
    service = spring_service_with_auth

    result = service.invoke_endpoint(
        "sensor_measurements_latest", path_params={"sensor_external_id": "SII-002"}
    )

    assert result["status_code"] == 200
    assert len(FakeHttpxClient.api_calls) == 2
    assert len(FakeHttpxClient.login_calls) == 2
