"""Testes da ponte read-only de contexto canônico."""

import json
import stat
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.api import routes
from app.core.config import settings
from app.services.canonical_context import CanonicalContextService, CanonicalContextSourceError
from app.services.canonical_snapshot import CanonicalSnapshotError, CanonicalSnapshotRepository
from deploy.context_sync import procelbot_context_sync as sync


NOW = datetime(2026, 8, 11, 18, 0, tzinfo=timezone.utc)


def _snapshot(generated_at=NOW):
    return {
        "schema_version": 1,
        "generated_at": generated_at.isoformat(),
        "source": {"kind": "postgresql_read_only_export"},
        "profiles": {"user-1": {"id": "user-1", "nome": "Pessoa de Teste"}},
        "activities_by_user": {
            "user-1": [
                {
                    "id": "activity-1",
                    "missao_id": "mission-1",
                    "status": "PENDENTE",
                    "assigned_at": NOW.isoformat(),
                    "started_at": None,
                    "completed_at": None,
                    "mission_type": "Individual",
                    "mission_title": "Missão",
                    "mission_value": 10,
                }
            ]
        },
        "rooms": {"room-1": {"id": "room-1", "nome": "Sala", "capacidade": 4}},
        "presence_by_room": {
            "room-1": {
                "records_count": 1,
                "occupied_count": 1,
                "latest_open_checkin_at": NOW.isoformat(),
                "latest_event_at": NOW.isoformat(),
            }
        },
        "room_telemetry": {
            "room-1": {
                "id": "measurement-1",
                "timestamp": NOW.isoformat(),
                "source": "postgresql_snapshot",
                "sensorExternalId": "sensor-1",
                "compartimentoId": "room-1",
                "valores": {"temperature_c": 22.5},
                "unidades": {"temperature_c": "C"},
            }
        },
        "sensor_telemetry": {},
        "missions": [
            {
                "id": "mission-1",
                "tipo": "Individual",
                "titulo": "Missão",
                "descricao": None,
                "value": 10,
                "ativo": True,
                "parent_id": None,
                "created_at": NOW.isoformat(),
            }
        ],
        "parameter_definitions": [],
    }


def _write(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.chmod(0o640)


def test_snapshot_repository_serves_sanitized_contracts(tmp_path):
    path = tmp_path / "latest.json"
    _write(path, _snapshot())
    repository = CanonicalSnapshotRepository(path)

    assert repository.fetch_canonical_user_profile("user-1") == {
        "id": "user-1",
        "nome": "Pessoa de Teste",
    }
    assert repository.fetch_canonical_activities("user-1", 1)[0]["id"] == "activity-1"
    assert repository.fetch_latest_room_measurement("room-1")["valores"] == {
        "temperature_c": 22.5
    }
    assert repository.snapshot_generated_at() == NOW


def test_snapshot_age_controls_canonical_freshness(tmp_path, monkeypatch):
    path = tmp_path / "latest.json"
    _write(path, _snapshot(NOW - timedelta(minutes=10)))
    monkeypatch.setattr(settings, "context_max_age_seconds", 300)
    service = CanonicalContextService(
        db_service=CanonicalSnapshotRepository(path),
        clock=lambda: NOW,
    )

    profile = service.profile("user-1")

    assert profile["metadata"]["source"] == "snapshot"
    assert profile["metadata"]["status"] == "stale"
    assert profile["metadata"]["age_seconds"] == 600


def test_context_service_selects_snapshot_backend_from_settings(tmp_path, monkeypatch):
    path = tmp_path / "latest.json"
    _write(path, _snapshot())
    monkeypatch.setattr(settings, "canonical_context_source", "snapshot")
    monkeypatch.setattr(settings, "canonical_snapshot_path", str(path))

    service = CanonicalContextService(clock=lambda: NOW)

    assert isinstance(service.db_service, CanonicalSnapshotRepository)
    assert service.profile("user-1")["metadata"]["source"] == "snapshot"


def test_snapshot_reader_rejects_symlink_and_oversized_file(tmp_path):
    target = tmp_path / "target.json"
    _write(target, _snapshot())
    link = tmp_path / "latest.json"
    link.symlink_to(target)

    with pytest.raises(CanonicalSnapshotError):
        CanonicalSnapshotRepository(link).fetch_canonical_user_profile("user-1")

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b"x" * 1025)
    with pytest.raises(CanonicalSnapshotError):
        CanonicalSnapshotRepository(oversized, max_bytes=1024).fetch_canonical_user_profile(
            "user-1"
        )


def test_snapshot_reader_rejects_world_readable_file(tmp_path):
    path = tmp_path / "latest.json"
    _write(path, _snapshot())
    path.chmod(0o644)

    with pytest.raises(CanonicalSnapshotError, match="permissões"):
        CanonicalSnapshotRepository(path).fetch_canonical_user_profile("user-1")


def test_consistent_view_pins_one_generation_during_replace(tmp_path):
    path = tmp_path / "latest.json"
    first = _snapshot()
    second = _snapshot(NOW + timedelta(minutes=1))
    second["presence_by_room"]["room-1"]["occupied_count"] = 0
    _write(path, first)
    repository = CanonicalSnapshotRepository(path)

    with repository.consistent_view():
        room = repository.fetch_room_by_id("room-1")
        replacement = tmp_path / "replacement.json"
        _write(replacement, second)
        replacement.replace(path)
        presence = repository.fetch_canonical_presence("room-1")

    assert room["nome"] == "Sala"
    assert presence["occupied_count"] == 1
    assert repository.fetch_canonical_presence("room-1")["occupied_count"] == 0


def test_future_snapshot_is_stale_with_clock_skew(tmp_path, monkeypatch):
    path = tmp_path / "latest.json"
    _write(path, _snapshot(NOW + timedelta(seconds=60)))
    monkeypatch.setattr(settings, "context_max_age_seconds", 300)
    service = CanonicalContextService(
        db_service=CanonicalSnapshotRepository(path),
        clock=lambda: NOW,
    )

    metadata = service.profile("user-1")["metadata"]

    assert metadata["status"] == "stale"
    assert metadata["fresh"] is False
    assert metadata["clock_skew"] is True


def test_missing_snapshot_maps_to_source_unavailable(tmp_path):
    service = CanonicalContextService(
        db_service=CanonicalSnapshotRepository(tmp_path / "missing.json"),
        clock=lambda: NOW,
    )

    with pytest.raises(CanonicalContextSourceError, match="snapshot"):
        service.profile("user-1")


class FakeCursor:
    def __init__(self):
        self.queries = []
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=()):
        normalized = " ".join(str(query).split()).casefold()
        self.queries.append(normalized)
        if normalized == "set transaction isolation level repeatable read, read only":
            self.rows = []
        elif "from public.pessoa" in normalized:
            self.rows = [{"id": "user-1", "nome": "Pessoa", "email": "não consultado"}]
        elif "from ranked" in normalized:
            self.rows = []
        elif "from public.compartimento" in normalized:
            self.rows = [{"id": "room-1", "nome": "Sala", "capacidade": 2}]
        elif "from public.presenca" in normalized:
            self.rows = []
        elif "from public.missao" in normalized:
            self.rows = []
        elif "from public.parametro_def" in normalized and "with latest" not in normalized:
            self.rows = []
        elif "with latest" in normalized:
            self.rows = []
        else:
            raise AssertionError(normalized)

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self._cursor


class FakeExportService:
    def __init__(self):
        self.cursor = FakeCursor()

    def _connect(self):
        return FakeConnection(self.cursor)


def test_export_is_read_only_and_snapshot_has_no_connection_secrets():
    service = FakeExportService()

    snapshot = sync.export_snapshot(service)

    assert service.cursor.queries[0] == (
        "set transaction isolation level repeatable read, read only"
    )
    assert sum("partition by ativo" in query for query in service.cursor.queries) == 2
    assert snapshot["source"] == {"kind": "postgresql_read_only_export"}
    serialized = json.dumps(snapshot)
    for forbidden in ("password", "remote_pg_host", "remote_pg_user", "telefone"):
        assert forbidden not in serialized.casefold()


def test_snapshot_writer_is_atomic_and_group_read_only(tmp_path):
    output = tmp_path / "latest.json"

    sync.write_snapshot(_snapshot(), output)

    assert json.loads(output.read_text(encoding="utf-8"))["schema_version"] == 1
    assert stat.S_IMODE(output.stat().st_mode) == 0o640
    assert not list(tmp_path.glob("*.tmp"))


def test_snapshot_writer_refuses_oversized_payload_without_replacing_last_good(tmp_path):
    output = tmp_path / "latest.json"
    sync.write_snapshot(_snapshot(), output)
    original = output.read_bytes()

    with pytest.raises(ValueError, match="excede"):
        sync.write_snapshot({**_snapshot(), "large": "x" * 2048}, output, max_bytes=1024)

    assert output.read_bytes() == original


def test_sync_refuses_insecure_non_loopback_transport(monkeypatch):
    monkeypatch.setattr(settings, "remote_pg_sslmode", "disable")
    monkeypatch.setattr(settings, "remote_pg_host", "187.77.58.122")

    with pytest.raises(RuntimeError, match="localhost"):
        sync.validate_transport()

    monkeypatch.setattr(settings, "remote_pg_host", "127.0.0.1")
    sync.validate_transport()


def test_health_uses_snapshot_without_probing_remote_database(monkeypatch):
    class FakeContextService:
        def missions(self, limit):
            assert limit == 1
            return {"metadata": {"status": "fresh"}}

    class FakeSpringService:
        def get_connection_info(self):
            raise RuntimeError("spring disabled")

    monkeypatch.setattr(settings, "canonical_context_source", "snapshot")
    monkeypatch.setattr(routes, "get_canonical_context_service", lambda: FakeContextService())
    monkeypatch.setattr(
        routes,
        "get_remote_postgres_catalog_service",
        lambda: pytest.fail("o backend não deve abrir conexão PostgreSQL direta"),
    )
    monkeypatch.setattr(routes, "get_spring_api_catalog_service", lambda: FakeSpringService())

    components = routes._probe_external_components()

    assert components["database"] == "snapshot_fresh"


def test_backend_production_example_contains_no_postgres_credentials():
    example = (
        Path(__file__).parents[1] / "deploy/backend/backend.env.example"
    ).read_text(encoding="utf-8")

    assert "REMOTE_PG_PASSWORD=" not in example


def test_context_sync_script_runs_directly_outside_repository(tmp_path):
    script = (
        Path(__file__).parents[1]
        / "deploy/context_sync/procelbot_context_sync.py"
    )

    completed = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "--output" in completed.stdout
