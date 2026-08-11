"""Repositório read-only para snapshots canônicos sanitizados."""

from __future__ import annotations

import json
import os
import stat
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings


SNAPSHOT_SCHEMA_VERSION = 1


class CanonicalSnapshotError(Exception):
    """O snapshot está ausente, inseguro, inválido ou incompatível."""


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class CanonicalSnapshotRepository:
    """Implementa a interface de leitura usada por ``CanonicalContextService``."""

    source_name = "snapshot"

    def __init__(self, path: str | Path | None = None, max_bytes: int | None = None) -> None:
        self.path = Path(path or settings.canonical_snapshot_path)
        self.max_bytes = max_bytes or settings.canonical_snapshot_max_bytes
        self._local = threading.local()

    def _read_payload(self) -> dict[str, Any]:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(self.path, flags)
        except OSError as exc:
            raise CanonicalSnapshotError("Snapshot canônico não está disponível.") from exc

        try:
            file_stat = os.fstat(descriptor)
            if not stat.S_ISREG(file_stat.st_mode):
                raise CanonicalSnapshotError("Snapshot canônico não é um arquivo regular.")
            # 0640 é o esperado: leitura do grupo é necessária ao container,
            # mas escrita/execução pelo grupo e qualquer acesso de outros são recusados.
            if stat.S_IMODE(file_stat.st_mode) & 0o027:
                raise CanonicalSnapshotError("Snapshot canônico possui permissões inseguras.")
            if file_stat.st_size <= 0 or file_stat.st_size > self.max_bytes:
                raise CanonicalSnapshotError("Snapshot canônico possui tamanho inválido.")
            with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
                descriptor = -1
                payload = json.load(stream)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CanonicalSnapshotError("Snapshot canônico possui JSON inválido.") from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)

        if not isinstance(payload, dict) or payload.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
            raise CanonicalSnapshotError("Versão do snapshot canônico não suportada.")
        generated_at = _parse_datetime(payload.get("generated_at"))
        if generated_at is None:
            raise CanonicalSnapshotError("Snapshot canônico não possui generated_at válido.")

        mapping_fields = (
            "profiles",
            "activities_by_user",
            "rooms",
            "presence_by_room",
            "room_telemetry",
            "sensor_telemetry",
        )
        if any(not isinstance(payload.get(field), dict) for field in mapping_fields):
            raise CanonicalSnapshotError("Snapshot canônico possui mapas inválidos.")
        if not isinstance(payload.get("missions"), list) or not isinstance(
            payload.get("parameter_definitions"), list
        ):
            raise CanonicalSnapshotError("Snapshot canônico possui listas inválidas.")

        self._local.generated_at = generated_at
        return payload

    def _load(self) -> dict[str, Any]:
        pinned = getattr(self._local, "pinned_payload", None)
        return pinned if pinned is not None else self._read_payload()

    @contextmanager
    def consistent_view(self):
        """Fixa uma geração na thread durante uma operação composta."""
        depth = getattr(self._local, "view_depth", 0)
        if depth == 0:
            self._local.pinned_payload = self._read_payload()
        self._local.view_depth = depth + 1
        try:
            yield
        finally:
            self._local.view_depth -= 1
            if self._local.view_depth == 0:
                self._local.pinned_payload = None
                self._local.generated_at = None

    def snapshot_generated_at(self) -> datetime:
        generated_at = getattr(self._local, "generated_at", None)
        if generated_at is None:
            self._load()
            generated_at = self._local.generated_at
        return generated_at

    def fetch_canonical_user_profile(self, pessoa_id: str) -> dict[str, Any] | None:
        return self._load()["profiles"].get(str(pessoa_id))

    def fetch_canonical_activities(self, pessoa_id: str, limit: int) -> list[dict[str, Any]]:
        rows = self._load()["activities_by_user"].get(str(pessoa_id), [])
        return list(rows[:limit])

    def fetch_room_by_id(self, room_id: str) -> dict[str, Any] | None:
        return self._load()["rooms"].get(str(room_id))

    def fetch_canonical_presence(self, room_id: str) -> dict[str, Any]:
        return self._load()["presence_by_room"].get(
            str(room_id),
            {
                "records_count": 0,
                "occupied_count": 0,
                "latest_open_checkin_at": None,
                "latest_event_at": None,
            },
        )

    def fetch_latest_room_measurement(self, room_id: str) -> dict[str, Any] | None:
        return self._load()["room_telemetry"].get(str(room_id))

    def fetch_latest_sensor_measurement(self, sensor_id: str) -> dict[str, Any] | None:
        return self._load()["sensor_telemetry"].get(str(sensor_id))

    def fetch_canonical_missions(self, active_only: bool, limit: int) -> list[dict[str, Any]]:
        rows = self._load()["missions"]
        if active_only:
            rows = [row for row in rows if row.get("ativo") is True]
        return list(rows[:limit])

    def fetch_canonical_parameter_definitions(
        self,
        active_only: bool,
        limit: int,
    ) -> list[dict[str, Any]]:
        rows = self._load()["parameter_definitions"]
        if active_only:
            rows = [row for row in rows if row.get("ativo") is True]
        return list(rows[:limit])
