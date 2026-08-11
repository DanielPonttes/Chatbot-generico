"""Testes dos contratos canônicos de contexto read-only."""

from datetime import datetime, timedelta, timezone

import pytest
from unittest.mock import AsyncMock

from app.api import routes
from app.core.config import settings
from app.services.canonical_context import (
    CanonicalContextService,
    CanonicalContextSourceError,
)
from app.services.notification_context_assembler import (
    NotificationContextAssembler,
    NotificationContextConflictError,
    NotificationContextStateError,
)
from app.services.persona_service import ProactiveMessageResult


NOW = datetime(2026, 8, 11, 15, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def canonical_tests_use_tls(monkeypatch):
    monkeypatch.setattr(settings, "remote_pg_sslmode", "require")


class FakeCanonicalDatabase:
    def fetch_canonical_user_profile(self, pessoa_id):
        if pessoa_id == "missing":
            return None
        return {
            "id": pessoa_id,
            "nome": "Pessoa de Teste",
            "email": "nao-deve-aparecer@example.com",
            "telefone": "+55 00 00000-0000",
            "created_at": NOW - timedelta(days=10),
        }

    def fetch_canonical_activities(self, pessoa_id, limit):
        return [
            {
                "id": "activity-1",
                "missao_id": "mission-1",
                "status": "PENDENTE",
                "assigned_at": NOW - timedelta(minutes=10),
                "started_at": None,
                "completed_at": None,
                "mission_type": "Individual",
                "mission_title": "Teste",
                "mission_value": 10,
            }
        ][:limit]

    def fetch_latest_room_measurement(self, room_id):
        if room_id == "empty":
            return None
        observed_at = NOW - timedelta(seconds=30 if room_id == "fresh" else 600)
        return {
            "id": "measurement-1",
            "timestamp": observed_at,
            "source": "fixture",
            "sensorExternalId": "sensor-1",
            "compartimentoId": room_id,
            "valores": {"temperature_c": 22.5, "presence": True},
            "unidades": {"temperature_c": "C", "presence": None},
        }

    def fetch_latest_sensor_measurement(self, sensor_id):
        return self.fetch_latest_room_measurement(sensor_id)

    def fetch_room_by_id(self, room_id):
        if room_id == "missing":
            return None
        return {"id": room_id, "nome": "Sala de Teste", "capacidade": 4}

    def fetch_canonical_presence(self, room_id):
        return {
            "records_count": 3,
            "occupied_count": 2,
            "latest_open_checkin_at": NOW - timedelta(minutes=2),
            "latest_event_at": NOW - timedelta(minutes=2),
        }

    def fetch_canonical_missions(self, active_only, limit):
        return [
            {
                "id": "mission-1",
                "tipo": "Individual",
                "titulo": "Teste",
                "descricao": None,
                "value": 10,
                "ativo": True,
                "parent_id": None,
                "created_at": NOW - timedelta(days=1),
            }
        ][:limit]

    def fetch_canonical_parameter_definitions(self, active_only, limit):
        return [
            {
                "id": "parameter-1",
                "data_type": "NUMERIC",
                "numeric_unit": "C",
                "tipo_nome": "SENSOR",
                "nome": "temperature_c",
                "descricao": "Temperatura",
                "ativo": True,
            }
        ][:limit]


class FailingCanonicalDatabase:
    def fetch_canonical_user_profile(self, pessoa_id):
        raise RuntimeError("source down")


def test_profile_redacts_personal_fields_and_uses_snapshot_freshness():
    service = CanonicalContextService(db_service=FakeCanonicalDatabase(), clock=lambda: NOW)

    result = service.profile("user-1")

    assert result["data"] == {"user_id": "user-1", "display_name": "Pessoa de Teste"}
    assert "email" not in result["data"]
    assert result["metadata"]["status"] == "fresh"
    assert result["metadata"]["fresh"] is True


def test_telemetry_marks_stale_and_preserves_units(monkeypatch):
    monkeypatch.setattr(settings, "context_max_age_seconds", 300)
    service = CanonicalContextService(db_service=FakeCanonicalDatabase(), clock=lambda: NOW)

    fresh = service.room_telemetry("fresh")
    stale = service.room_telemetry("stale")

    assert fresh["metadata"]["status"] == "fresh"
    assert stale["metadata"]["status"] == "stale"
    assert stale["metadata"]["fresh"] is False
    assert fresh["data"]["metrics"][0]["unit"] == "C"


def test_empty_telemetry_is_explicit():
    service = CanonicalContextService(db_service=FakeCanonicalDatabase(), clock=lambda: NOW)

    result = service.room_telemetry("empty")

    assert result["data"] is None
    assert result["metadata"]["status"] == "empty"
    assert result["metadata"]["fresh"] is False


def test_future_observation_fails_closed_and_marks_clock_skew(monkeypatch):
    monkeypatch.setattr(settings, "context_max_age_seconds", 300)
    database = FakeCanonicalDatabase()
    original = database.fetch_latest_room_measurement
    database.fetch_latest_room_measurement = lambda room_id: {
        **original(room_id),
        "timestamp": NOW + timedelta(seconds=5),
    }
    service = CanonicalContextService(db_service=database, clock=lambda: NOW)

    result = service.room_telemetry("fresh")

    assert result["metadata"]["fresh"] is False
    assert result["metadata"]["status"] == "stale"
    assert result["metadata"]["clock_skew"] is True


def test_presence_calculates_percentage_without_person_ids():
    service = CanonicalContextService(db_service=FakeCanonicalDatabase(), clock=lambda: NOW)

    result = service.room_presence("room-1")

    assert result["data"]["occupied_count"] == 2
    assert result["data"]["occupancy_pct"] == 50.0
    assert "pessoa_id" not in result["data"]


def test_presence_uses_event_timestamp_for_freshness(monkeypatch):
    monkeypatch.setattr(settings, "context_max_age_seconds", 300)
    database = FakeCanonicalDatabase()
    database.fetch_canonical_presence = lambda room_id: {
        "records_count": 1,
        "occupied_count": 1,
        "latest_open_checkin_at": NOW + timedelta(seconds=5),
        "latest_event_at": NOW + timedelta(seconds=5),
    }
    service = CanonicalContextService(db_service=database, clock=lambda: NOW)

    result = service.room_presence("room-1")

    assert result["metadata"]["fresh"] is False
    assert result["metadata"]["clock_skew"] is True


def test_open_presence_remains_fresh_when_checkin_is_old(monkeypatch):
    monkeypatch.setattr(settings, "context_max_age_seconds", 300)
    database = FakeCanonicalDatabase()
    database.fetch_canonical_presence = lambda room_id: {
        "records_count": 1,
        "occupied_count": 1,
        "latest_open_checkin_at": NOW - timedelta(seconds=600),
        "latest_event_at": NOW - timedelta(seconds=600),
    }
    service = CanonicalContextService(db_service=database, clock=lambda: NOW)

    result = service.room_presence("room-1")

    assert result["metadata"]["fresh"] is True
    assert result["metadata"]["status"] == "fresh"


def test_empty_occupancy_is_current_snapshot_even_with_old_last_event(monkeypatch):
    monkeypatch.setattr(settings, "context_max_age_seconds", 300)
    database = FakeCanonicalDatabase()
    database.fetch_canonical_presence = lambda room_id: {
        "records_count": 1,
        "occupied_count": 0,
        "latest_open_checkin_at": None,
        "latest_event_at": NOW - timedelta(seconds=600),
    }
    service = CanonicalContextService(db_service=database, clock=lambda: NOW)

    result = service.room_presence("room-1")

    assert result["data"]["occupied_count"] == 0
    assert result["metadata"]["fresh"] is True


def test_canonical_context_requires_postgres_tls(monkeypatch):
    monkeypatch.setattr(settings, "remote_pg_sslmode", "disable")
    service = CanonicalContextService(db_service=FakeCanonicalDatabase(), clock=lambda: NOW)

    with pytest.raises(CanonicalContextSourceError, match="TLS"):
        service.profile("user-1")


def test_canonical_context_accepts_stricter_tls_modes(monkeypatch):
    monkeypatch.setattr(settings, "remote_pg_sslmode", "verify-full")
    service = CanonicalContextService(db_service=FakeCanonicalDatabase(), clock=lambda: NOW)

    result = service.profile("user-1")

    assert result["data"]["user_id"] == "user-1"


def test_presence_ignores_invalid_capacity_without_500():
    database = FakeCanonicalDatabase()
    database.fetch_room_by_id = lambda room_id: {
        "id": room_id,
        "nome": "Sala de Teste",
        "capacidade": "not-a-number",
    }
    service = CanonicalContextService(db_service=database, clock=lambda: NOW)

    result = service.room_presence("room-1")

    assert result["data"]["capacity"] is None
    assert result["data"]["occupancy_pct"] is None


def test_source_failure_is_fail_closed():
    service = CanonicalContextService(db_service=FailingCanonicalDatabase(), clock=lambda: NOW)

    with pytest.raises(CanonicalContextSourceError):
        service.profile("user-1")


class FakeNotificationCanonicalService:
    def __init__(self, *, telemetry_status="fresh"):
        self.telemetry_status = telemetry_status

    @staticmethod
    def _metadata(scope, source_status="fresh"):
        return {
            "source": "postgresql",
            "scope": scope,
            "status": source_status,
            "fresh": source_status == "fresh",
            "observed_at": NOW,
            "fetched_at": NOW,
            "age_seconds": 0,
            "max_age_seconds": 300,
        }

    def profile(self, pessoa_id):
        return {
            "metadata": self._metadata(f"user:{pessoa_id}"),
            "data": {"user_id": pessoa_id, "display_name": "Daniel da Silva"},
        }

    def room_telemetry(self, room_id):
        return {
            "metadata": self._metadata(
                f"room:{room_id}:telemetry", self.telemetry_status
            ),
            "data": {
                "metrics": [
                    {"name": "temperature_c", "value": 22.5, "unit": "C"},
                    {"name": "secret_metric", "value": "não propagar", "unit": None},
                ]
            },
        }

    def room_presence(self, room_id):
        return {
            "metadata": self._metadata(f"room:{room_id}:presence"),
            "data": {"occupied_count": 0},
        }

    def sensor_telemetry(self, sensor_id):
        return {
            "metadata": self._metadata(f"sensor:{sensor_id}:telemetry"),
            "data": {"metrics": [{"name": "humidity_pct", "value": 55, "unit": "%"}]},
        }


def test_notification_context_assembler_adds_only_allowed_fresh_source_fields():
    assembler = NotificationContextAssembler(FakeNotificationCanonicalService())

    result = assembler.assemble(
        provided_context={"target_action": "apagar a luz"},
        allowed_fields={
            "target_action",
            "room_id",
            "presence_status",
            "temperature_internal",
        },
        pessoa_id="user-1",
        room_id="room-1",
    )

    assert result.values == {
        "target_action": "apagar a luz",
        "user_first_name": "Daniel",
        "room_id": "room-1",
        "temperature_internal": 22.5,
        "presence_status": "vazia",
    }
    assert "secret_metric" not in result.values
    assert result.source_fields == (
        "presence_status",
        "room_id",
        "temperature_internal",
        "user_first_name",
    )


def test_notification_context_assembler_ignores_whitespace_display_name():
    service = FakeNotificationCanonicalService()
    service.profile = lambda pessoa_id: {
        "metadata": service._metadata(f"user:{pessoa_id}"),
        "data": {"user_id": pessoa_id, "display_name": "   \t"},
    }
    assembler = NotificationContextAssembler(service)

    result = assembler.assemble(
        provided_context={},
        allowed_fields=set(),
        pessoa_id="user-1",
    )

    assert "user_first_name" not in result.values


def test_notification_context_assembler_rejects_client_source_conflict():
    assembler = NotificationContextAssembler(FakeNotificationCanonicalService())

    with pytest.raises(NotificationContextConflictError) as exc_info:
        assembler.assemble(
            provided_context={"room_id": "room-spoofed"},
            allowed_fields={"room_id"},
            room_id="room-1",
        )

    assert exc_info.value.field == "room_id"


def test_notification_context_assembler_rejects_stale_snapshot():
    assembler = NotificationContextAssembler(
        FakeNotificationCanonicalService(telemetry_status="stale")
    )

    with pytest.raises(NotificationContextStateError) as exc_info:
        assembler.assemble(
            provided_context={},
            allowed_fields={"room_id"},
            room_id="room-1",
        )

    assert exc_info.value.source_status == "stale"


class FakeContextService:
    def profile(self, user_id):
        return {
            "metadata": {
                "source": "postgresql",
                "scope": f"user:{user_id}",
                "status": "fresh",
                "fresh": True,
                "observed_at": NOW,
                "fetched_at": NOW,
                "age_seconds": 0,
                "max_age_seconds": 300,
            },
            "data": {"user_id": user_id, "display_name": "Pessoa de Teste"},
        }

    def activities(self, user_id, limit):
        return {
            "metadata": {
                "source": "postgresql",
                "scope": f"user:{user_id}:activities",
                "status": "fresh",
                "fresh": True,
                "observed_at": NOW,
                "fetched_at": NOW,
                "age_seconds": 0,
                "max_age_seconds": 300,
            },
            "data": {
                "user_id": user_id,
                "items": [],
                "total": 0,
                "by_status": {},
                "latest_event_at": None,
                "limit": limit,
            },
        }


def test_context_routes_require_admin_key(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "admin-context-key")
    monkeypatch.setattr(routes, "get_canonical_context_service", lambda: FakeContextService())

    response = client.get("/v1/context/users/user-1/profile")

    assert response.status_code == 401


def test_context_routes_reject_public_api_key(client, monkeypatch):
    monkeypatch.setattr(settings, "api_key", "public-context-key")
    monkeypatch.setattr(settings, "admin_api_key", "admin-context-key")
    monkeypatch.setattr(routes, "get_canonical_context_service", lambda: FakeContextService())

    response = client.get(
        "/v1/context/users/user-1/profile",
        headers={"X-API-Key": "public-context-key"},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "admin_scope_required"


def test_context_routes_return_typed_contract(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "admin-context-key")
    monkeypatch.setattr(routes, "get_canonical_context_service", lambda: FakeContextService())

    response = client.get(
        "/v1/context/users/user-1/activities?limit=10",
        headers={"X-API-Key": "admin-context-key"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["metadata"]["source"] == "postgresql"
    assert payload["data"]["limit"] == 10


def test_notification_generation_canonical_context_requires_admin_key(client, monkeypatch):
    monkeypatch.setattr(settings, "api_key", "public-context-key")
    monkeypatch.setattr(settings, "admin_api_key", "admin-context-key")
    monkeypatch.setattr(
        routes,
        "get_canonical_context_service",
        lambda: FakeNotificationCanonicalService(),
    )

    response = client.post(
        "/v1/notifications/generate",
        headers={"X-API-Key": "public-context-key"},
        json={
            "mission_id": "ultimo_a_apagar",
            "persona_id": "motivador",
            "use_canonical_context": True,
            "room_id": "room-1",
            "notification_context": {
                "target_action": "apagar a iluminação",
                "target_time_window": "agora",
                "reward_description": "10 EcoCoins",
            },
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "admin_scope_required"


def test_notification_generation_uses_canonical_values_without_legacy_lookup(
    client,
    monkeypatch,
    patched_services,
):
    monkeypatch.setattr(settings, "admin_api_key", "admin-context-key")
    monkeypatch.setattr(
        routes,
        "get_canonical_context_service",
        lambda: FakeNotificationCanonicalService(),
    )
    generated = ProactiveMessageResult(
        message="Apague a luz ao sair.",
        context_summary=None,
        prompt_used="prompt de teste",
    )
    generator = AsyncMock(return_value=generated)
    monkeypatch.setattr(routes.PersonaService, "generate_proactive_message", generator)
    saved_items = []
    monkeypatch.setattr(
        routes,
        "save_notification",
        lambda item: saved_items.append(item) or True,
    )

    response = client.post(
        "/v1/notifications/generate",
        headers={"X-API-Key": "admin-context-key"},
        json={
            "mission_id": "ultimo_a_apagar",
            "persona_id": "motivador",
            "use_canonical_context": True,
            "pessoa_id": "user-1",
            "room_id": "room-1",
            "notification_context": {
                "target_action": "apagar a iluminação",
                "target_time_window": "agora",
                "reward_description": "10 EcoCoins",
            },
        },
    )

    assert response.status_code == 200
    kwargs = generator.await_args.kwargs
    assert kwargs["pessoa_id"] is None
    assert kwargs["room_id"] is None
    assert kwargs["sensor_external_id"] is None
    assert kwargs["notification_context"]["user_first_name"] == "Daniel"
    assert kwargs["notification_context"]["presence_status"] == "vazia"
    assert kwargs["notification_context"]["room_id"] == "room-1"
    assert saved_items[0]["prompt_used"] is None


def test_notification_generation_rejects_canonical_context_conflict(
    client,
    monkeypatch,
):
    monkeypatch.setattr(settings, "admin_api_key", "admin-context-key")
    monkeypatch.setattr(
        routes,
        "get_canonical_context_service",
        lambda: FakeNotificationCanonicalService(),
    )

    response = client.post(
        "/v1/notifications/generate",
        headers={"X-API-Key": "admin-context-key"},
        json={
            "mission_id": "ultimo_a_apagar",
            "persona_id": "motivador",
            "use_canonical_context": True,
            "room_id": "room-1",
            "notification_context": {
                "room_id": "room-spoofed",
                "target_action": "apagar a iluminação",
                "target_time_window": "agora",
                "reward_description": "10 EcoCoins",
            },
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "error": "canonical_context_conflict",
        "message": "O campo 'room_id' diverge da fonte canônica e não pode sobrescrevê-la.",
        "details": {"field": "room_id"},
    }


def test_notification_generation_revalidates_limits_after_canonical_merge(
    client,
    monkeypatch,
):
    monkeypatch.setattr(settings, "admin_api_key", "admin-context-key")
    monkeypatch.setattr(
        routes,
        "get_canonical_context_service",
        lambda: FakeNotificationCanonicalService(),
    )
    context = {f"extra_{index}": index for index in range(29)}
    context.update(
        {
            "target_action": "apagar a iluminação",
            "target_time_window": "agora",
            "reward_description": "10 EcoCoins",
        }
    )

    response = client.post(
        "/v1/notifications/generate",
        headers={"X-API-Key": "admin-context-key"},
        json={
            "mission_id": "ultimo_a_apagar",
            "persona_id": "motivador",
            "use_canonical_context": True,
            "pessoa_id": "user-1",
            "room_id": "room-1",
            "notification_context": context,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "canonical_context_limits_exceeded"


def test_notification_generation_rejects_stale_context_before_llm(
    client,
    monkeypatch,
):
    monkeypatch.setattr(settings, "admin_api_key", "admin-context-key")
    monkeypatch.setattr(
        routes,
        "get_canonical_context_service",
        lambda: FakeNotificationCanonicalService(telemetry_status="stale"),
    )
    generator = AsyncMock()
    monkeypatch.setattr(routes.PersonaService, "generate_proactive_message", generator)

    response = client.post(
        "/v1/notifications/generate",
        headers={"X-API-Key": "admin-context-key"},
        json={
            "mission_id": "ultimo_a_apagar",
            "persona_id": "motivador",
            "use_canonical_context": True,
            "room_id": "room-1",
            "notification_context": {
                "target_action": "apagar a iluminação",
                "target_time_window": "agora",
                "reward_description": "10 EcoCoins",
            },
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "canonical_context_not_fresh"
    generator.assert_not_awaited()


def test_notification_generation_maps_source_failure_to_503(
    client,
    monkeypatch,
):
    class FailingNotificationCanonicalService(FakeNotificationCanonicalService):
        def room_telemetry(self, room_id):
            raise CanonicalContextSourceError("fonte indisponível")

    monkeypatch.setattr(settings, "admin_api_key", "admin-context-key")
    monkeypatch.setattr(
        routes,
        "get_canonical_context_service",
        lambda: FailingNotificationCanonicalService(),
    )
    generator = AsyncMock()
    monkeypatch.setattr(routes.PersonaService, "generate_proactive_message", generator)

    response = client.post(
        "/v1/notifications/generate",
        headers={"X-API-Key": "admin-context-key"},
        json={
            "mission_id": "ultimo_a_apagar",
            "persona_id": "motivador",
            "use_canonical_context": True,
            "room_id": "room-1",
            "notification_context": {
                "target_action": "apagar a iluminação",
                "target_time_window": "agora",
                "reward_description": "10 EcoCoins",
            },
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "context_source_unavailable"
    generator.assert_not_awaited()
