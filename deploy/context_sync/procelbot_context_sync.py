#!/usr/bin/env python3
"""Exporta contratos canônicos para um snapshot local sanitizado.

Este processo é a única peça que recebe a credencial PostgreSQL. A transação é
marcada como READ ONLY antes da primeira consulta e o snapshot não inclui host,
usuário, senha, e-mail, telefone, matrícula nem identificadores de presença.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import time
from ipaddress import ip_address
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

# Execução direta define sys.path para deploy/context_sync; inclua a raiz do
# checkout antes de importar o pacote da aplicação.
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from app.core.config import settings
from app.services.canonical_snapshot import SNAPSHOT_SCHEMA_VERSION
from app.services.integration_catalog import (
    RemotePostgresCatalogService,
    get_remote_postgres_catalog_service,
)


LOGGER = logging.getLogger("procelbot-context-sync")
ALLOWED_TELEMETRY_METRICS = (
    "presence",
    "energy_total_room",
    "power_kw",
    "temperature_c",
    "internal_temperature_c",
    "temperature_internal",
    "humidity_pct",
    "co2_ppm",
    "noise_db",
    "ruido_ambiente",
    "occupancy_pct",
    "ac_status",
    "ac_setpoint_c",
    "light_status",
    "status_iluminacao",
    "light_level_pct",
    "illuminance_lux",
    "luminosity_level",
    "lux_level",
    "current_lux_reading",
    "measured_consumption_kwh",
    "cooling_consumption_kwh",
    "consumo_circuito",
    "door_window_sensor_status",
)


def validate_transport() -> None:
    """Recusa PostgreSQL remoto sem TLS; localhost representa túnel criptografado."""
    if settings.remote_pg_sslmode in {"require", "verify-ca", "verify-full"}:
        return
    host = settings.remote_pg_host.strip().strip("[]")
    is_loopback = host.casefold() == "localhost"
    if not is_loopback:
        try:
            is_loopback = ip_address(host).is_loopback
        except ValueError:
            is_loopback = False
    if not is_loopback:
        raise RuntimeError(
            "Transporte PostgreSQL sem TLS só é aceito via túnel em localhost."
        )


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:1024]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)[:1024]


def _fetch_all(cursor, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cursor.execute(query, params)
    return list(cursor.fetchall())


def _pick(row: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    """Aplica allowlist mesmo que um driver/fake devolva colunas inesperadas."""
    return {field: row.get(field) for field in fields}


def _measurement_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    measurements: dict[str, dict[str, Any]] = {}
    for row in rows:
        target_key = str(row["target_key"])
        measurement = measurements.setdefault(
            target_key,
            {
                "id": str(row["id"]),
                "timestamp": row["timestamp"],
                "source": row.get("source") or "postgresql_snapshot",
                "sensorExternalId": row.get("sensor_external_id"),
                "compartimentoId": row.get("compartimento_id"),
                "valores": {},
                "unidades": {},
            },
        )
        value = row.get("numeric_value")
        if value is None:
            value = row.get("boolean_value")
        if value is None:
            value = row.get("text_value")
        measurement["valores"][row["metric"]] = value
        measurement["unidades"][row["metric"]] = row.get("unit")
    return measurements


def export_snapshot(service: RemotePostgresCatalogService) -> dict[str, Any]:
    """Executa uma transação PostgreSQL consistente e somente leitura."""
    with service._connect() as connection, connection.cursor() as cursor:
        # Deve ser a primeira instrução. READ ONLY limita este código durante
        # o ciclo; o isolamento operacional da credencial continua dependendo
        # da unit endurecida e do arquivo de ambiente protegido.
        cursor.execute(
            "set transaction isolation level repeatable read, read only"
        )

        profiles = _fetch_all(
            cursor,
            "select id, nome from public.pessoa order by id",
        )
        activities = _fetch_all(
            cursor,
            """
            with ranked as (
                select
                    a.pessoa_id,
                    a.id,
                    a.missao_id,
                    a.status,
                    a.assigned_at,
                    a.started_at,
                    a.completed_at,
                    m.tipo as mission_type,
                    m.titulo as mission_title,
                    m.value as mission_value,
                    row_number() over (
                        partition by a.pessoa_id
                        order by coalesce(a.completed_at, a.started_at, a.assigned_at) desc
                    ) as position
                from public.atividade a
                left join public.missao m on m.id = a.missao_id
            )
            select * from ranked where position <= %s order by pessoa_id, position
            """,
            (settings.context_max_items,),
        )
        rooms = _fetch_all(
            cursor,
            "select id, nome, capacidade from public.compartimento order by id",
        )
        presence = _fetch_all(
            cursor,
            """
            select
                compartimento_id,
                count(*)::int as records_count,
                count(*) filter (where checkout_at is null)::int as occupied_count,
                max(checkin_at) filter (where checkout_at is null) as latest_open_checkin_at,
                max(coalesce(checkout_at, checkin_at)) as latest_event_at
            from public.presenca
            group by compartimento_id
            order by compartimento_id
            """,
        )
        missions = _fetch_all(
            cursor,
            """
            with ranked as (
                select
                    id, tipo, titulo, descricao, value, ativo, parent_id, created_at,
                    row_number() over (
                        partition by ativo order by created_at desc, id
                    ) as position
                from public.missao
            )
            select id, tipo, titulo, descricao, value, ativo, parent_id, created_at
            from ranked
            where position <= %s
            order by created_at desc, id
            """,
            (settings.context_max_items,),
        )
        parameter_definitions = _fetch_all(
            cursor,
            """
            with ranked as (
                select
                    id, data_type, numeric_unit, tipo_nome, nome, descricao, ativo,
                    row_number() over (
                        partition by ativo order by tipo_nome, nome, id
                    ) as position
                from public.parametro_def
            )
            select id, data_type, numeric_unit, tipo_nome, nome, descricao, ativo
            from ranked
            where position <= %s
            order by tipo_nome, nome, id
            """,
            (settings.context_max_items,),
        )

        sensor_measurements = _fetch_all(
            cursor,
            """
            with latest as (
                select distinct on (sensor_external_id) id
                from public.medicao
                where sensor_external_id is not null
                order by sensor_external_id, timestamp desc
            )
            select
                m.sensor_external_id as target_key,
                m.id,
                m.timestamp,
                m.source,
                m.sensor_external_id,
                s.compartimento_id,
                pd.nome as metric,
                pd.numeric_unit as unit,
                pv.numeric_value,
                pv.boolean_value,
                pv.text_value
            from latest l
            join public.medicao m on m.id = l.id
            join public.parametro_valor pv on pv.medicao_id = m.id
            join public.parametro_def pd on pd.id = pv.parametro_def_id
            left join public.sensor s on s.external_id = m.sensor_external_id
            where pd.nome = any(%s)
            order by m.sensor_external_id, pd.nome
            """,
            (list(ALLOWED_TELEMETRY_METRICS),),
        )
        room_measurements = _fetch_all(
            cursor,
            """
            with latest as (
                select distinct on (s.compartimento_id)
                    s.compartimento_id,
                    m.id
                from public.medicao m
                join public.sensor s on s.external_id = m.sensor_external_id
                where s.compartimento_id is not null
                order by s.compartimento_id, m.timestamp desc
            )
            select
                l.compartimento_id as target_key,
                m.id,
                m.timestamp,
                m.source,
                m.sensor_external_id,
                l.compartimento_id,
                pd.nome as metric,
                pd.numeric_unit as unit,
                pv.numeric_value,
                pv.boolean_value,
                pv.text_value
            from latest l
            join public.medicao m on m.id = l.id
            join public.parametro_valor pv on pv.medicao_id = m.id
            join public.parametro_def pd on pd.id = pv.parametro_def_id
            where pd.nome = any(%s)
            order by l.compartimento_id, pd.nome
            """,
            (list(ALLOWED_TELEMETRY_METRICS),),
        )

    activities_by_user: dict[str, list[dict[str, Any]]] = {}
    for row in activities:
        user_id = str(row.get("pessoa_id"))
        activities_by_user.setdefault(user_id, []).append(
            _pick(
                row,
                (
                    "id",
                    "missao_id",
                    "status",
                    "assigned_at",
                    "started_at",
                    "completed_at",
                    "mission_type",
                    "mission_title",
                    "mission_value",
                ),
            )
        )

    snapshot = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc),
        "source": {"kind": "postgresql_read_only_export"},
        "profiles": {
            str(row["id"]): _pick(row, ("id", "nome")) for row in profiles
        },
        "activities_by_user": activities_by_user,
        "rooms": {
            str(row["id"]): _pick(row, ("id", "nome", "capacidade"))
            for row in rooms
        },
        "presence_by_room": {
            str(row["compartimento_id"]): _pick(
                row,
                (
                    "records_count",
                    "occupied_count",
                    "latest_open_checkin_at",
                    "latest_event_at",
                ),
            )
            for row in presence
        },
        "room_telemetry": _measurement_map(room_measurements),
        "sensor_telemetry": _measurement_map(sensor_measurements),
        "missions": [
            _pick(
                row,
                (
                    "id",
                    "tipo",
                    "titulo",
                    "descricao",
                    "value",
                    "ativo",
                    "parent_id",
                    "created_at",
                ),
            )
            for row in missions
        ],
        "parameter_definitions": [
            _pick(
                row,
                (
                    "id",
                    "data_type",
                    "numeric_unit",
                    "tipo_nome",
                    "nome",
                    "descricao",
                    "ativo",
                ),
            )
            for row in parameter_definitions
        ],
    }
    return _json_safe(snapshot)


def write_snapshot(
    snapshot: dict[str, Any],
    output: Path,
    max_bytes: int | None = None,
) -> None:
    serialized = (
        json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    size_limit = max_bytes or settings.canonical_snapshot_max_bytes
    if len(serialized) > size_limit:
        raise ValueError(
            f"snapshot excede o limite configurado de {size_limit} bytes"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o640)
        os.replace(temporary, output)
        directory_fd = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--interval", type=float, default=60.0)
    parser.add_argument("--once", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.interval <= 0:
        raise SystemExit("--interval deve ser maior que zero")
    if not settings.remote_pg_password:
        raise SystemExit("REMOTE_PG_PASSWORD não configurada para o sincronizador")
    try:
        validate_transport()
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    service = get_remote_postgres_catalog_service()
    while True:
        started_at = time.monotonic()
        try:
            snapshot = export_snapshot(service)
            write_snapshot(snapshot, args.output)
            LOGGER.info(
                "snapshot atualizado: perfis=%d salas=%d missões=%d",
                len(snapshot["profiles"]),
                len(snapshot["rooms"]),
                len(snapshot["missions"]),
            )
        except Exception as exc:
            # Mantém o último snapshot válido. Nunca registra configuração nem
            # credenciais; detalhes do driver ficam fora do log operacional.
            LOGGER.error("falha ao atualizar snapshot canônico: %s", type(exc).__name__)
            if args.once:
                return 1
        if args.once:
            return 0
        elapsed = time.monotonic() - started_at
        time.sleep(max(0.1, args.interval - elapsed))


if __name__ == "__main__":
    raise SystemExit(main())
