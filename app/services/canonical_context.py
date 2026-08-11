"""Adapters read-only para os contratos canônicos de contexto.

Este módulo é deliberadamente estreito: normaliza somente dados observados no
PostgreSQL e não calcula pontuação, ranking ou valores ausentes. A fonte é
consultada através do catálogo existente, com limites e freshness explícitos.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable

from app.core.config import settings
from app.services.integration_catalog import (
    RemoteDatabaseError,
    get_remote_postgres_catalog_service,
)
from app.services.canonical_snapshot import (
    CanonicalSnapshotError,
    CanonicalSnapshotRepository,
)

logger = logging.getLogger(__name__)


class CanonicalContextError(Exception):
    """Erro base dos adapters canônicos."""


class CanonicalContextNotFoundError(CanonicalContextError):
    """O escopo solicitado não existe na fonte canônica."""


class CanonicalContextSourceError(CanonicalContextError):
    """A fonte canônica está indisponível ou não respondeu."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _json_value(value: Any) -> Any:
    """Converte apenas valores conhecidos do driver para JSON seguro."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return _as_utc(value)
    return str(value)


class CanonicalContextService:
    """Monta envelopes canônicos sem expor PII desnecessária."""

    def __init__(self, db_service=None, clock: Callable[[], datetime] | None = None) -> None:
        if db_service is not None:
            self.db_service = db_service
        elif settings.canonical_context_source == "snapshot":
            self.db_service = CanonicalSnapshotRepository()
        else:
            self.db_service = get_remote_postgres_catalog_service()
        self.source_name = getattr(self.db_service, "source_name", "postgresql")
        self.clock = clock or _utcnow

    def _snapshot_observed_at(self, fallback: datetime) -> datetime:
        snapshot_clock = getattr(self.db_service, "snapshot_generated_at", None)
        if snapshot_clock is None:
            return fallback
        value = _as_utc(snapshot_clock())
        if value is None:
            raise CanonicalContextSourceError(
                "O snapshot canônico não possui timestamp de geração válido."
            )
        return value

    @contextmanager
    def consistent_view(self):
        view = getattr(self.db_service, "consistent_view", None)
        if view is None:
            yield
            return
        with view():
            yield

    def _call(self, operation: str, callback: Callable[[], Any]) -> Any:
        if (
            self.source_name == "postgresql"
            and settings.remote_pg_sslmode not in {"require", "verify-ca", "verify-full"}
        ):
            raise CanonicalContextSourceError(
                "O contexto canônico exige TLS (require, verify-ca ou verify-full)."
            )
        try:
            return callback()
        except RemoteDatabaseError as exc:
            logger.warning(
                "Fonte canônica indisponível durante %s: %s",
                operation,
                type(exc).__name__,
            )
            raise CanonicalContextSourceError(
                "A fonte PostgreSQL não está disponível para o contexto solicitado."
            ) from exc
        except CanonicalSnapshotError as exc:
            logger.warning("Snapshot canônico indisponível durante %s: %s", operation, exc)
            raise CanonicalContextSourceError(
                "O snapshot canônico não está disponível para o contexto solicitado."
            ) from exc
        except Exception as exc:
            logger.warning(
                "Falha na fonte canônica durante %s: %s",
                operation,
                type(exc).__name__,
            )
            raise CanonicalContextSourceError(
                "A fonte canônica não respondeu ao contexto solicitado."
            ) from exc

    def _metadata(
        self,
        scope: str,
        fetched_at: datetime,
        observed_at: datetime | None,
    ) -> dict[str, Any]:
        if observed_at is None:
            return {
                "source": self.source_name,
                "scope": scope,
                "status": "empty",
                "fresh": False,
                "observed_at": None,
                "fetched_at": fetched_at,
                "age_seconds": None,
                "max_age_seconds": settings.context_max_age_seconds,
                "clock_skew": False,
            }

        raw_age_seconds = (fetched_at - observed_at).total_seconds()
        clock_skew = raw_age_seconds < 0
        if clock_skew:
            logger.warning(
                "Timestamp observado no futuro para o escopo canônico %s: %.3fs",
                scope,
                abs(raw_age_seconds),
            )
        age_seconds = max(0.0, raw_age_seconds)
        fresh = not clock_skew and age_seconds <= settings.context_max_age_seconds
        return {
            "source": self.source_name,
            "scope": scope,
            "status": "fresh" if fresh else "stale",
            "fresh": fresh,
            "observed_at": observed_at,
            "fetched_at": fetched_at,
            "age_seconds": round(age_seconds, 3),
            "max_age_seconds": settings.context_max_age_seconds,
            "clock_skew": clock_skew,
        }

    def profile(self, pessoa_id: str) -> dict[str, Any]:
        fetched_at = self.clock()
        row = self._call(
            "perfil",
            lambda: self.db_service.fetch_canonical_user_profile(pessoa_id),
        )
        if row is None:
            raise CanonicalContextNotFoundError("Pessoa não encontrada na fonte canônica.")

        # O perfil canônico não carrega e-mail, telefone, senha ou matrícula.
        return {
            "metadata": self._metadata(
                f"user:{pessoa_id}",
                fetched_at,
                self._snapshot_observed_at(fetched_at),
            ),
            "data": {
                "user_id": str(row["id"]),
                "display_name": row.get("nome") or None,
            },
        }

    def activities(self, pessoa_id: str, limit: int | None = None) -> dict[str, Any]:
        fetched_at = self.clock()
        safe_limit = max(1, min(limit or settings.context_max_items, settings.context_max_items))
        rows = self._call(
            "atividades",
            lambda: self.db_service.fetch_canonical_activities(pessoa_id, limit=safe_limit),
        )

        by_status: dict[str, int] = {}
        items: list[dict[str, Any]] = []
        latest_event: datetime | None = None
        for row in rows:
            status = str(row["status"])
            by_status[status] = by_status.get(status, 0) + 1
            timestamps = [
                _as_utc(row.get("assigned_at")),
                _as_utc(row.get("started_at")),
                _as_utc(row.get("completed_at")),
            ]
            row_latest = max((item for item in timestamps if item is not None), default=None)
            if row_latest and (latest_event is None or row_latest > latest_event):
                latest_event = row_latest
            items.append(
                {
                    "activity_id": str(row["id"]),
                    "mission_id": str(row["missao_id"]),
                    "status": status,
                    "assigned_at": _as_utc(row.get("assigned_at")),
                    "started_at": _as_utc(row.get("started_at")),
                    "completed_at": _as_utc(row.get("completed_at")),
                    "mission_type": row.get("mission_type"),
                    "mission_title": row.get("mission_title"),
                    "mission_value": row.get("mission_value"),
                }
            )

        # A consulta é um snapshot atual; os timestamps dos eventos ficam nos
        # itens e não tornam a lista inteira stale apenas por serem históricos.
        return {
            "metadata": self._metadata(
                f"user:{pessoa_id}:activities",
                fetched_at,
                self._snapshot_observed_at(fetched_at),
            ),
            "data": {
                "user_id": pessoa_id,
                "items": items,
                "total": len(items),
                "by_status": by_status,
                "latest_event_at": latest_event,
                "limit": safe_limit,
            },
        }

    def _telemetry(
        self,
        scope: str,
        target_id: str,
        fetcher: Callable[[], dict[str, Any] | None],
    ) -> dict[str, Any]:
        fetched_at = self.clock()
        row = self._call(f"telemetria:{scope}", fetcher)
        if row is None:
            return {
                "metadata": self._metadata(scope, fetched_at, None),
                "data": None,
            }

        observed_at = _as_utc(row.get("timestamp"))
        units = row.get("unidades", {})
        values = row.get("valores", {})
        metrics = [
            {
                "name": name,
                "value": _json_value(value),
                "unit": units.get(name),
            }
            for name, value in values.items()
        ]
        return {
            "metadata": self._metadata(scope, fetched_at, observed_at),
            "data": {
                "measurement_id": str(row["id"]),
                "target_id": target_id,
                "sensor_external_id": row.get("sensorExternalId"),
                "room_id": row.get("compartimentoId"),
                "source": row.get("source") or self.source_name,
                "observed_at": observed_at,
                "metrics": metrics,
            },
        }

    def room_telemetry(self, room_id: str) -> dict[str, Any]:
        return self._telemetry(
            f"room:{room_id}:telemetry",
            room_id,
            lambda: self.db_service.fetch_latest_room_measurement(room_id),
        )

    def sensor_telemetry(self, sensor_id: str) -> dict[str, Any]:
        return self._telemetry(
            f"sensor:{sensor_id}:telemetry",
            sensor_id,
            lambda: self.db_service.fetch_latest_sensor_measurement(sensor_id),
        )

    def room_presence(self, room_id: str) -> dict[str, Any]:
        with self.consistent_view():
            return self._room_presence(room_id)

    def _room_presence(self, room_id: str) -> dict[str, Any]:
        fetched_at = self.clock()
        room = self._call("sala-presença", lambda: self.db_service.fetch_room_by_id(room_id))
        if room is None:
            raise CanonicalContextNotFoundError("Sala não encontrada na fonte canônica.")
        presence = self._call(
            "presença",
            lambda: self.db_service.fetch_canonical_presence(room_id),
        )
        raw_capacity = room.get("capacidade")
        try:
            capacity = int(raw_capacity) if raw_capacity is not None else None
        except (TypeError, ValueError):
            logger.warning("Capacidade inválida para a sala canônica %s", room_id)
            capacity = None
        occupied_count = int(presence.get("occupied_count") or 0)
        occupancy_pct = None
        if capacity is not None and capacity > 0:
            occupancy_pct = round(occupied_count * 100 / capacity, 2)

        event_timestamps = [
            _as_utc(presence.get("latest_open_checkin_at")),
            _as_utc(presence.get("latest_event_at")),
        ]
        latest_event_at = max(
            (item for item in event_timestamps if item is not None),
            default=None,
        )
        records_count = int(presence.get("records_count") or 0)
        # A consulta devolve o estado atual dos check-ins. Um check-in aberto
        # antigo continua sendo ocupação corrente; só um timestamp no futuro
        # deve invalidar a freshness do snapshot.
        if latest_event_at is None and records_count == 0:
            observed_at = None
        elif latest_event_at is not None and latest_event_at > fetched_at:
            observed_at = latest_event_at
        else:
            observed_at = self._snapshot_observed_at(fetched_at)

        return {
            "metadata": self._metadata(f"room:{room_id}:presence", fetched_at, observed_at),
            "data": {
                "room_id": room_id,
                "room_name": room.get("nome"),
                "occupied_count": occupied_count,
                "capacity": capacity,
                "occupancy_pct": occupancy_pct,
                "records_count": records_count,
                "latest_open_checkin_at": _as_utc(presence.get("latest_open_checkin_at")),
                "latest_event_at": latest_event_at,
                "as_of": fetched_at,
            },
        }

    def missions(self, active_only: bool = True, limit: int | None = None) -> dict[str, Any]:
        fetched_at = self.clock()
        safe_limit = max(1, min(limit or settings.context_max_items, settings.context_max_items))
        rows = self._call(
            "missões",
            lambda: self.db_service.fetch_canonical_missions(active_only, safe_limit),
        )
        return {
            "metadata": self._metadata(
                "missions", fetched_at, self._snapshot_observed_at(fetched_at)
            ),
            "data": {
                "active_only": active_only,
                "items": [
                    {
                        "mission_id": str(row["id"]),
                        "type": row.get("tipo"),
                        "title": row.get("titulo"),
                        "description": row.get("descricao"),
                        "value": row.get("value"),
                        "active": row.get("ativo"),
                        "parent_id": str(row["parent_id"]) if row.get("parent_id") else None,
                        "created_at": _as_utc(row.get("created_at")),
                    }
                    for row in rows
                ],
                "total": len(rows),
                "limit": safe_limit,
            },
        }

    def parameter_definitions(
        self,
        active_only: bool = True,
        limit: int | None = None,
    ) -> dict[str, Any]:
        fetched_at = self.clock()
        safe_limit = max(1, min(limit or settings.context_max_items, settings.context_max_items))
        rows = self._call(
            "definições de parâmetros",
            lambda: self.db_service.fetch_canonical_parameter_definitions(active_only, safe_limit),
        )
        return {
            "metadata": self._metadata(
                "rules:parameter-definitions",
                fetched_at,
                self._snapshot_observed_at(fetched_at),
            ),
            "data": {
                "active_only": active_only,
                "items": [
                    {
                        "parameter_id": str(row["id"]),
                        "data_type": row.get("data_type"),
                        "unit": row.get("numeric_unit"),
                        "sensor_type": row.get("tipo_nome"),
                        "name": row.get("nome"),
                        "description": row.get("descricao"),
                        "active": row.get("ativo"),
                    }
                    for row in rows
                ],
                "total": len(rows),
                "limit": safe_limit,
            },
        }


_canonical_context_service: CanonicalContextService | None = None


def get_canonical_context_service() -> CanonicalContextService:
    global _canonical_context_service
    if _canonical_context_service is None:
        _canonical_context_service = CanonicalContextService()
    return _canonical_context_service
