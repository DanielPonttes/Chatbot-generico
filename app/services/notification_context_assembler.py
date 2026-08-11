"""Assembler seguro de contexto canônico para geração de notificações.

O assembler transforma somente campos observados em variáveis conhecidas do
catálogo. Ele não calcula ranking, recompensas, baselines ou qualquer outro
valor que dependa de regra de negócio ainda não confirmada.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from app.services.canonical_context import CanonicalContextService


class NotificationContextAssemblyError(Exception):
    """Erro base do assembler de contexto de notificações."""


class NotificationContextSelectionError(NotificationContextAssemblyError):
    """A montagem foi solicitada sem um seletor canônico."""


class NotificationContextStateError(NotificationContextAssemblyError):
    """Um snapshot solicitado está vazio, stale ou com clock skew."""

    def __init__(self, scope: str, source_status: str) -> None:
        self.scope = scope
        self.source_status = source_status
        super().__init__(
            f"O contexto canônico '{scope}' está com status '{source_status}' e não pode ser usado."
        )


class NotificationContextConflictError(NotificationContextAssemblyError):
    """Um valor fornecido diverge do valor observado na fonte canônica."""

    def __init__(self, field: str) -> None:
        self.field = field
        super().__init__(
            f"O campo '{field}' diverge da fonte canônica e não pode sobrescrevê-la."
        )


@dataclass(frozen=True)
class AssembledNotificationContext:
    """Contexto validado e os escopos canônicos que contribuíram para ele."""

    values: dict[str, Any]
    source_fields: tuple[str, ...]
    scopes: tuple[str, ...]


# Aliases estritamente semânticos. Conversões de consumo, baseline, ranking e
# recompensa ficam de fora porque exigiriam unidade ou regra de negócio ainda
# não confirmada.
_TELEMETRY_ALIASES: dict[str, tuple[str, ...]] = {
    "temperature_c": ("temperature_internal",),
    "internal_temperature_c": ("temperature_internal",),
    "illuminance_lux": ("lux_level", "current_lux_reading"),
    "light_status": ("status_iluminacao",),
}


class NotificationContextAssembler:
    """Combina input do cliente com snapshots canônicos, falhando fechado."""

    def __init__(self, context_service: CanonicalContextService) -> None:
        self.context_service = context_service

    def assemble(
        self,
        *,
        provided_context: dict[str, Any] | None,
        allowed_fields: Iterable[str],
        pessoa_id: str | None = None,
        room_id: str | None = None,
        sensor_external_id: str | None = None,
    ) -> AssembledNotificationContext:
        with self.context_service.consistent_view():
            return self._assemble(
                provided_context=provided_context,
                allowed_fields=allowed_fields,
                pessoa_id=pessoa_id,
                room_id=room_id,
                sensor_external_id=sensor_external_id,
            )

    def _assemble(
        self,
        *,
        provided_context: dict[str, Any] | None,
        allowed_fields: Iterable[str],
        pessoa_id: str | None = None,
        room_id: str | None = None,
        sensor_external_id: str | None = None,
    ) -> AssembledNotificationContext:
        if not any((pessoa_id, room_id, sensor_external_id)):
            raise NotificationContextSelectionError(
                "use_canonical_context exige pessoa_id, room_id ou sensor_external_id."
            )

        allowed = set(allowed_fields)
        # user_first_name é suportado transversalmente pelo template técnico.
        allowed.add("user_first_name")
        observed: dict[str, Any] = {}
        scopes: list[str] = []

        if pessoa_id:
            profile = self.context_service.profile(pessoa_id)
            self._require_fresh(profile)
            scopes.append(profile["metadata"]["scope"])
            display_name = (profile.get("data") or {}).get("display_name")
            if display_name:
                name_parts = str(display_name).split()
                if name_parts:
                    self._add_observed(observed, "user_first_name", name_parts[0])

        if room_id:
            telemetry = self.context_service.room_telemetry(room_id)
            self._require_fresh(telemetry)
            scopes.append(telemetry["metadata"]["scope"])
            self._add_observed(observed, "room_id", room_id, allowed)
            self._add_telemetry(observed, telemetry, allowed)

            presence = self.context_service.room_presence(room_id)
            self._require_fresh(presence)
            scopes.append(presence["metadata"]["scope"])
            if "presence_status" in allowed:
                occupied_count = presence["data"]["occupied_count"]
                self._add_observed(
                    observed,
                    "presence_status",
                    "ocupada" if occupied_count > 0 else "vazia",
                )

        if sensor_external_id:
            telemetry = self.context_service.sensor_telemetry(sensor_external_id)
            self._require_fresh(telemetry)
            scopes.append(telemetry["metadata"]["scope"])
            self._add_observed(
                observed,
                "sensor_external_id",
                sensor_external_id,
                allowed,
            )
            self._add_telemetry(observed, telemetry, allowed)

        merged = dict(provided_context or {})
        for field, value in observed.items():
            if field in merged and merged[field] != value:
                raise NotificationContextConflictError(field)
            merged[field] = value

        return AssembledNotificationContext(
            values=merged,
            source_fields=tuple(sorted(observed)),
            scopes=tuple(scopes),
        )

    @staticmethod
    def _require_fresh(envelope: dict[str, Any]) -> None:
        metadata = envelope["metadata"]
        if metadata.get("status") != "fresh" or not metadata.get("fresh"):
            raise NotificationContextStateError(
                str(metadata.get("scope") or "unknown"),
                str(metadata.get("status") or "unknown"),
            )

    def _add_telemetry(
        self,
        observed: dict[str, Any],
        envelope: dict[str, Any],
        allowed: set[str],
    ) -> None:
        data = envelope.get("data") or {}
        for metric in data.get("metrics", []):
            name = metric.get("name")
            if not isinstance(name, str):
                continue
            value = metric.get("value")
            self._add_observed(observed, name, value, allowed)
            for alias in _TELEMETRY_ALIASES.get(name, ()):
                self._add_observed(observed, alias, value, allowed)

    @staticmethod
    def _add_observed(
        observed: dict[str, Any],
        field: str,
        value: Any,
        allowed: set[str] | None = None,
    ) -> None:
        if allowed is not None and field not in allowed:
            return
        if field in observed and observed[field] != value:
            raise NotificationContextConflictError(field)
        observed[field] = value
