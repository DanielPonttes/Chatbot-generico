"""
Monta contexto operacional real para notificações proativas.

Combina:
- metadados estruturais do PostgreSQL remoto
- medições e cadastro exposto pelo backend Spring Boot
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.services.integration_catalog import (
    RemoteDatabaseError,
    RemoteSpringApiError,
    get_remote_postgres_catalog_service,
    get_spring_api_catalog_service,
)

logger = logging.getLogger(__name__)


METRIC_PRIORITY = (
    "presence",
    "energy_total_room",
    "power_kw",
    "temperature_c",
    "humidity_pct",
    "co2_ppm",
    "noise_db",
    "occupancy_pct",
    "ac_status",
    "ac_setpoint_c",
    "light_status",
    "light_level_pct",
)


@dataclass
class ProactiveOperationalContext:
    """Resultado agregado para enriquecer o prompt de notificação."""

    summary: str | None = None
    prompt_block: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class ProactiveOperationalContextService:
    """Monta contexto real a partir de IDs opcionais de sala, sensor e pessoa."""

    def __init__(self, spring_service=None, db_service=None) -> None:
        self.spring_service = spring_service or get_spring_api_catalog_service()
        self.db_service = db_service or get_remote_postgres_catalog_service()

    def build_context(
        self,
        room_id: str | None = None,
        sensor_external_id: str | None = None,
        pessoa_id: str | None = None,
    ) -> ProactiveOperationalContext:
        if not any([room_id, sensor_external_id, pessoa_id]):
            return ProactiveOperationalContext()

        sections: list[str] = []
        summary_parts: list[str] = []
        metadata: dict[str, Any] = {}

        room = self._safe_fetch_room(room_id) if room_id else None
        if room:
            metadata["room"] = room
            summary_parts.append(f"Sala {room['nome']} (id={room['id']})")
            sections.append(self._format_room_section(room))

        sensor = self._safe_fetch_sensor(sensor_external_id) if sensor_external_id else None
        if sensor:
            metadata["sensor"] = sensor
            summary_parts.append(f"Sensor {sensor['external_id']}")
            sections.append(self._format_sensor_section(sensor))

        person = self._safe_fetch_person(pessoa_id) if pessoa_id else None
        if person:
            metadata["person"] = person
            summary_parts.append(f"Pessoa {person['nome']}")
            sections.append(self._format_person_section(person))

        room_measurement = (
            self._safe_fetch_measurement(
                latest_endpoint_id="room_measurements_latest",
                list_endpoint_id="room_measurements_list",
                path_params={"room_id": room_id},
                db_fallback=lambda: self._safe_fetch_db_measurement("room", room_id),
            )
            if room_id
            else None
        )
        if room_measurement:
            metadata["room_measurement"] = room_measurement
            summary_parts.append(self._short_measurement_summary("Sala", room_measurement))
            sections.append(self._format_measurement_section("Última medição da sala", room_measurement))

        sensor_measurement = (
            self._safe_fetch_measurement(
                latest_endpoint_id="sensor_measurements_latest",
                list_endpoint_id="sensor_measurements_list",
                path_params={"sensor_external_id": sensor_external_id},
                db_fallback=lambda: self._safe_fetch_db_measurement(
                    "sensor", sensor_external_id
                ),
            )
            if sensor_external_id
            else None
        )
        if sensor_measurement:
            metadata["sensor_measurement"] = sensor_measurement
            summary_parts.append(self._short_measurement_summary("Sensor", sensor_measurement))
            sections.append(
                self._format_measurement_section("Última medição do sensor", sensor_measurement)
            )

        if not sections:
            return ProactiveOperationalContext()

        prompt_block = (
            "\nCONTEXTO OPERACIONAL REAL DO PROJETO:\n"
            + "\n".join(f"- {section}" for section in sections)
            + "\nUse esse contexto real para citar a sala, o sensor, a ocupação ou o padrão de consumo "
              "somente quando isso tornar a notificação mais específica e útil."
        )

        summary = " | ".join(part for part in summary_parts if part).strip() or None
        return ProactiveOperationalContext(summary=summary, prompt_block=prompt_block, metadata=metadata)

    def _safe_fetch_room(self, room_id: str) -> dict[str, Any] | None:
        try:
            return self.db_service.fetch_room_by_id(room_id)
        except RemoteDatabaseError as exc:
            logger.warning("Falha ao buscar room_id=%s no PostgreSQL remoto: %s", room_id, exc)
            return None

    def _safe_fetch_sensor(self, sensor_external_id: str) -> dict[str, Any] | None:
        try:
            return self.db_service.fetch_sensor_by_external_id(sensor_external_id)
        except RemoteDatabaseError as exc:
            logger.warning(
                "Falha ao buscar sensor_external_id=%s no PostgreSQL remoto: %s",
                sensor_external_id,
                exc,
            )
            return None

    def _safe_fetch_person(self, pessoa_id: str) -> dict[str, Any] | None:
        try:
            response = self.spring_service.invoke_endpoint(
                endpoint_id="pessoas_get",
                path_params={"pessoa_id": pessoa_id},
            )
            if response["status_code"] == 200 and isinstance(response["data"], dict):
                return response["data"]
        except RemoteSpringApiError as exc:
            logger.warning("Falha ao buscar pessoa_id=%s no Spring remoto: %s", pessoa_id, exc)

        try:
            return self.db_service.fetch_person_by_id(pessoa_id)
        except RemoteDatabaseError as exc:
            logger.warning("Falha ao buscar pessoa_id=%s no PostgreSQL remoto: %s", pessoa_id, exc)
            return None

    def _safe_fetch_db_measurement(self, scope: str, key: str) -> dict[str, Any] | None:
        """Fallback: busca a última medição direto no PostgreSQL remoto."""
        try:
            if scope == "room":
                return self.db_service.fetch_latest_room_measurement(key)
            return self.db_service.fetch_latest_sensor_measurement(key)
        except RemoteDatabaseError as exc:
            logger.warning(
                "Falha ao buscar medição %s=%s no PostgreSQL remoto: %s", scope, key, exc
            )
            return None

    def _safe_fetch_measurement(
        self,
        latest_endpoint_id: str,
        list_endpoint_id: str,
        path_params: dict[str, str | None],
        db_fallback=None,
    ) -> dict[str, Any] | None:
        clean_path_params = {
            key: value for key, value in path_params.items() if value is not None
        }

        try:
            response = self.spring_service.invoke_endpoint(
                endpoint_id=latest_endpoint_id,
                path_params=clean_path_params,
            )
            if response["status_code"] == 200 and isinstance(response["data"], dict):
                return response["data"]
        except RemoteSpringApiError as exc:
            logger.warning("Falha ao consultar endpoint %s: %s", latest_endpoint_id, exc)

        measurement: dict[str, Any] | None = None
        try:
            response = self.spring_service.invoke_endpoint(
                endpoint_id=list_endpoint_id,
                path_params=clean_path_params,
            )
            if response["status_code"] == 200 and isinstance(response["data"], list):
                measurements = [item for item in response["data"] if isinstance(item, dict)]
                if measurements:
                    measurement = max(measurements, key=lambda item: item.get("timestamp", ""))
        except RemoteSpringApiError as exc:
            logger.warning("Falha ao consultar endpoint %s: %s", list_endpoint_id, exc)

        if measurement is not None:
            return measurement

        if db_fallback is not None:
            return db_fallback()
        return None

    def _format_room_section(self, room: dict[str, Any]) -> str:
        pieces = [f"sala {room['nome']} (id={room['id']})"]
        if room.get("tipo"):
            pieces.append(f"tipo {room['tipo']}")
        if room.get("pavimento") is not None:
            pieces.append(f"pavimento {room['pavimento']}")
        if room.get("predio_nome"):
            pieces.append(f"prédio {room['predio_nome']}")
        if room.get("unidade_nome"):
            pieces.append(f"unidade {room['unidade_nome']}")
        return ", ".join(pieces)

    def _format_sensor_section(self, sensor: dict[str, Any]) -> str:
        pieces = [f"sensor {sensor['external_id']}"]
        if sensor.get("nome"):
            pieces.append(f"nome {sensor['nome']}")
        if sensor.get("tipo_nome"):
            pieces.append(f"tipo {sensor['tipo_nome']}")
        if sensor.get("compartimento_id"):
            pieces.append(f"compartimento {sensor['compartimento_id']}")
        return ", ".join(pieces)

    def _format_person_section(self, person: dict[str, Any]) -> str:
        pieces = [f"pessoa {person['nome']} (id={person['id']})"]
        if person.get("matricula"):
            pieces.append(f"matrícula {person['matricula']}")
        if person.get("email"):
            pieces.append(f"email {person['email']}")
        return ", ".join(pieces)

    def _format_measurement_section(self, label: str, measurement: dict[str, Any]) -> str:
        timestamp = measurement.get("timestamp") or measurement.get("receivedAt")
        source = measurement.get("source")
        target = measurement.get("compartimentoId") or measurement.get("sensorExternalId")
        metrics = self._format_metrics(measurement.get("valores", {}))

        pieces = [label]
        if target:
            pieces.append(f"alvo {target}")
        if timestamp:
            pieces.append(f"em {self._format_timestamp(timestamp)}")
        if source:
            pieces.append(f"fonte {source}")
        if metrics:
            pieces.append(f"métricas {metrics}")

        return ", ".join(pieces)

    def _short_measurement_summary(self, label: str, measurement: dict[str, Any]) -> str:
        metrics = self._format_metrics(measurement.get("valores", {}), limit=3)
        if not metrics:
            return label
        return f"{label}: {metrics}"

    def _format_metrics(self, values: dict[str, Any], limit: int = 6) -> str:
        if not isinstance(values, dict) or not values:
            return ""

        ordered_keys = [
            key for key in METRIC_PRIORITY if key in values and values[key] is not None
        ]
        ordered_keys.extend(
            key
            for key in sorted(values)
            if key not in ordered_keys and values[key] is not None
        )

        formatted_pairs: list[str] = []
        for key in ordered_keys[:limit]:
            formatted_value = self._format_metric_value(key, values[key])
            formatted_pairs.append(f"{key}={formatted_value}")

        return ", ".join(formatted_pairs)

    def _format_metric_value(self, key: str, value: Any) -> str:
        if isinstance(value, bool):
            return "sim" if value else "nao"
        if isinstance(value, float):
            suffix = self._metric_suffix(key)
            return f"{value:.2f}".rstrip("0").rstrip(".") + suffix
        if isinstance(value, int):
            return f"{value}{self._metric_suffix(key)}"
        return str(value)

    def _metric_suffix(self, key: str) -> str:
        suffix_map = {
            "_c": " C",
            "_pct": "%",
            "_db": " dB",
            "_ppm": " ppm",
            "_kw": " kW",
        }
        for suffix, label in suffix_map.items():
            if key.endswith(suffix):
                return label
        return ""

    def _format_timestamp(self, value: str) -> str:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
        except ValueError:
            return value


_proactive_operational_context_service: ProactiveOperationalContextService | None = None


def get_proactive_operational_context_service() -> ProactiveOperationalContextService:
    global _proactive_operational_context_service
    if _proactive_operational_context_service is None:
        _proactive_operational_context_service = ProactiveOperationalContextService()
    return _proactive_operational_context_service
