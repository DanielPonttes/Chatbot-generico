"""
Testes para o enriquecimento contextual de notificações proativas.
"""

from unittest.mock import AsyncMock

from app.api import routes
from app.services.persona_service import ProactiveMessageResult
from app.services.proactive_context import ProactiveOperationalContextService


class FakeDbService:
    def fetch_room_by_id(self, room_id):
        assert room_id == "2"
        return {
            "id": "2",
            "nome": "Elevador",
            "tipo": "Circulacao",
            "pavimento": 4,
            "predio_nome": "(ANG) Anglo",
            "unidade_nome": "(PROPLAD) Pro-Reitoria",
        }

    def fetch_sensor_by_external_id(self, sensor_external_id):
        assert sensor_external_id == "SII-001"
        return {
            "external_id": "SII-001",
            "nome": "SII Smart - Sala 400D",
            "tipo_nome": "SII_SMART",
            "compartimento_id": "2",
        }

    def fetch_person_by_id(self, pessoa_id):
        assert pessoa_id == "ravilon"
        return {
            "id": "ravilon",
            "nome": "Ravilon A. Santos",
            "email": "ravilon@exemplo.com",
            "matricula": "MAT-001",
        }


class FakeSpringService:
    def invoke_endpoint(self, endpoint_id, path_params=None, query_params=None, body=None):
        if endpoint_id == "pessoas_get":
            return {
                "status_code": 200,
                "data": {
                    "id": "ravilon",
                    "nome": "Ravilon A. Santos",
                    "email": "ravilon@exemplo.com",
                    "matricula": "MAT-001",
                },
            }

        measurement = {
            "id": "m1",
            "sensorExternalId": "SII-001",
            "compartimentoId": "2",
            "timestamp": "2026-04-05T18:46:45.879123Z",
            "source": "mock",
            "valores": {
                "presence": True,
                "energy_total_room": 0.929,
                "temperature_c": 24.7,
                "humidity_pct": 72.1,
            },
        }
        return {"status_code": 200, "data": measurement}


def test_operational_context_builds_summary_and_prompt():
    service = ProactiveOperationalContextService(
        spring_service=FakeSpringService(),
        db_service=FakeDbService(),
    )

    result = service.build_context(
        room_id="2",
        sensor_external_id="SII-001",
        pessoa_id="ravilon",
    )

    assert "Sala Elevador" in result.summary
    assert "Sensor SII-001" in result.summary
    assert "Pessoa Ravilon A. Santos" in result.summary
    assert "temperature_c=24.7 C" in result.prompt_block
    assert "presence=sim" in result.prompt_block
    assert result.metadata["room"]["nome"] == "Elevador"


def test_operational_context_returns_empty_when_no_ids():
    service = ProactiveOperationalContextService(
        spring_service=FakeSpringService(),
        db_service=FakeDbService(),
    )

    result = service.build_context()

    assert result.summary is None
    assert result.prompt_block == ""
    assert result.metadata == {}


def test_chat_proactive_accepts_operational_context(client, patched_services, monkeypatch):
    generate_mock = AsyncMock(
        return_value=ProactiveMessageResult(
            message="Feche a luz da sala 2.",
            context_summary="Sala Elevador (id=2) | Sensor SII-001",
        )
    )
    monkeypatch.setattr(routes.PersonaService, "generate_proactive_message", generate_mock)

    response = client.post(
        "/chat/proactive",
        json={
            "persona_id": "provocador",
            "target_profile_id": "gastao",
            "room_id": "2",
            "sensor_external_id": "SII-001",
            "pessoa_id": "ravilon",
            "use_rag": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["reply"] == "Feche a luz da sala 2."
    assert data["context_summary"] == "Sala Elevador (id=2) | Sensor SII-001"

    generate_mock.assert_awaited_once_with(
        "provocador",
        target_profile_id="gastao",
        persona_override=None,
        model_override=None,
        use_rag=True,
        room_id="2",
        sensor_external_id="SII-001",
        pessoa_id="ravilon",
    )
