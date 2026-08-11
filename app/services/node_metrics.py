"""Leitor defensivo do snapshot local de métricas do host.

O backend não coleta métricas diretamente e não possui acesso ao Docker socket.
Ele apenas lê um arquivo montado como somente leitura e o expõe no endpoint
administrativo já protegido por autenticação separada.
"""

from __future__ import annotations

import json
import logging
import os
import stat as stat_module
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from app.core.config import settings
from app.models.schemas import NodeMetricsResponse


LOGGER = logging.getLogger(__name__)
MAX_SNAPSHOT_BYTES = 128 * 1024
SNAPSHOT_SCHEMA_VERSION = 1


def _parse_collected_at(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def read_node_metrics(path: str | None = None) -> NodeMetricsResponse | None:
    """Lê e valida um snapshot; arquivo ausente ou inválido não quebra a API."""
    snapshot_path = Path(path or settings.node_metrics_path)
    file_descriptor: int | None = None
    try:
        no_follow = getattr(os, "O_NOFOLLOW", 0)
        file_descriptor = os.open(snapshot_path, os.O_RDONLY | no_follow)
        file_stat = os.fstat(file_descriptor)
        if not stat_module.S_ISREG(file_stat.st_mode):
            LOGGER.warning("Snapshot de métricas não é um arquivo regular")
            return None
        if file_stat.st_size > MAX_SNAPSHOT_BYTES:
            LOGGER.warning("Snapshot de métricas excede o limite configurado")
            return None
        with os.fdopen(file_descriptor, "rb") as snapshot_file:
            file_descriptor = None
            raw_snapshot = snapshot_file.read(MAX_SNAPSHOT_BYTES + 1)
        if len(raw_snapshot) > MAX_SNAPSHOT_BYTES:
            LOGGER.warning("Snapshot de métricas excede o limite configurado")
            return None
        payload = json.loads(raw_snapshot.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        LOGGER.debug("Snapshot de métricas indisponível: %s", exc)
        return None
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)

    if not isinstance(payload, dict) or payload.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        LOGGER.warning("Snapshot de métricas com schema desconhecido")
        return None

    collected_at = _parse_collected_at(payload.get("collected_at"))
    if collected_at is None:
        LOGGER.warning("Snapshot de métricas sem collected_at válido")
        return None

    raw_age_seconds = (datetime.now(timezone.utc) - collected_at).total_seconds()
    clock_skew = raw_age_seconds < 0
    if clock_skew:
        LOGGER.warning(
            "Snapshot de métricas está no futuro por %.3fs; marcando como stale",
            abs(raw_age_seconds),
        )
    age_seconds = max(0.0, raw_age_seconds)
    max_age = max(0, int(settings.node_metrics_max_age_seconds))
    data = dict(payload)
    data["collected_at"] = collected_at
    data["age_seconds"] = round(age_seconds, 3)
    data["fresh"] = not clock_skew and age_seconds <= max_age
    data["clock_skew"] = clock_skew

    try:
        return NodeMetricsResponse.model_validate(data)
    except ValidationError as exc:
        LOGGER.warning("Snapshot de métricas não passou na validação: %s", exc.errors()[0]["type"])
        return None
