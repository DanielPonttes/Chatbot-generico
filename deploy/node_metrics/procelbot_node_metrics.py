#!/usr/bin/env python3
"""Coleta telemetria local do host e publica um snapshot atômico.

O processo não abre portas, não chama APIs externas e não acessa o Docker
socket. Ele apenas lê /proc, consulta nvidia-smi quando disponível, verifica o
estado de unidades systemd e escreve um JSON sem dados sensíveis.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import shutil
import socket
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LOGGER = logging.getLogger("procelbot-node-metrics")
SNAPSHOT_SCHEMA_VERSION = 1
CPU_WARMUP_SECONDS = 0.25
NVIDIA_QUERY = (
    "index,name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw"
)
SERVICE_UNITS = {
    "docker": "docker.service",
    "backend": "procelbot-backend.service",
    "ollama_stack": "procelbot-stack.service",
    "cloudflared": "cloudflared.service",
}


def _number(value: str) -> float | None:
    """Converte valores do driver, tratando N/A e campos vazios."""
    try:
        return float(value.strip())
    except (AttributeError, TypeError, ValueError):
        return None


def _bounded_percent(value: float | None) -> float | None:
    if value is None:
        return None
    return round(max(0.0, min(100.0, value)), 2)


class CpuSampler:
    """Calcula uso de CPU entre duas leituras de /proc/stat."""

    def __init__(self) -> None:
        self._previous: tuple[int, int] | None = None

    @staticmethod
    def _read_times() -> tuple[int, int] | None:
        try:
            with Path("/proc/stat").open(encoding="utf-8") as proc_stat:
                first_line = proc_stat.readline()
        except OSError:
            return None

        fields = first_line.split()
        if len(fields) < 5 or fields[0] != "cpu":
            return None
        try:
            values = [int(value) for value in fields[1:]]
        except ValueError:
            return None

        total = sum(values)
        # idle e iowait são os campos 4 e 5 da linha, após o identificador.
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        return total, idle

    def sample(self) -> float | None:
        current = self._read_times()
        if current is None:
            return None
        previous = self._previous
        self._previous = current
        if previous is None:
            return None

        total_delta = current[0] - previous[0]
        active_delta = (current[0] - current[1]) - (previous[0] - previous[1])
        if total_delta <= 0:
            return None
        return _bounded_percent((active_delta / total_delta) * 100.0)


def _read_meminfo() -> dict[str, int]:
    values: dict[str, int] = {}
    try:
        with Path("/proc/meminfo").open(encoding="utf-8") as meminfo:
            for line in meminfo:
                key, separator, remainder = line.partition(":")
                if not separator:
                    continue
                parts = remainder.strip().split()
                if not parts:
                    continue
                try:
                    value = int(parts[0])
                except ValueError:
                    continue
                # /proc/meminfo reports values in KiB when a unit is present.
                values[key] = value * 1024 if len(parts) > 1 and parts[1] == "kB" else value
    except OSError:
        return {}
    return values


def _collect_memory() -> tuple[int | None, int | None, float | None]:
    values = _read_meminfo()
    total = values.get("MemTotal")
    available = values.get("MemAvailable")
    if available is None and total is not None:
        available = sum(
            values.get(key, 0)
            for key in ("MemFree", "Buffers", "Cached", "SReclaimable")
        )
    if total is None or available is None or total <= 0:
        return total, available, None
    used_percent = _bounded_percent(((total - available) / total) * 100.0)
    return total, available, used_percent


def _collect_disk() -> tuple[int, int, float | None]:
    try:
        usage = shutil.disk_usage("/")
    except OSError:
        return 0, 0, None
    used_percent = _bounded_percent((usage.used / usage.total) * 100.0) if usage.total else None
    return usage.total, usage.used, used_percent


def _nvidia_smi_path() -> str | None:
    discovered = shutil.which("nvidia-smi")
    if discovered:
        return discovered
    fallback = Path("/usr/bin/nvidia-smi")
    return str(fallback) if fallback.exists() else None


def _collect_gpus() -> tuple[bool, list[dict[str, Any]]]:
    executable = _nvidia_smi_path()
    if executable is None:
        return False, []

    try:
        result = subprocess.run(
            [
                executable,
                f"--query-gpu={NVIDIA_QUERY}",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        LOGGER.debug("nvidia-smi indisponível: %s", exc)
        return False, []

    if result.returncode != 0:
        LOGGER.debug("nvidia-smi retornou código %s", result.returncode)
        return False, []

    gpus: list[dict[str, Any]] = []
    for row in csv.reader(result.stdout.splitlines()):
        fields = [field.strip() for field in row]
        if len(fields) < 7:
            continue
        try:
            index = int(fields[0])
        except ValueError:
            continue

        memory_used_mb = _number(fields[3])
        memory_total_mb = _number(fields[4])
        gpu: dict[str, Any] = {
            "index": index,
            "name": fields[1] or "unknown",
            "utilization_percent": _bounded_percent(_number(fields[2])),
            "memory_used_bytes": int(memory_used_mb * 1024 * 1024) if memory_used_mb is not None else None,
            "memory_total_bytes": int(memory_total_mb * 1024 * 1024) if memory_total_mb is not None else None,
            "temperature_c": _number(fields[5]),
            "power_w": _number(fields[6]),
        }
        gpus.append(gpu)
    return bool(gpus), gpus


def _service_state(unit: str) -> str:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", unit],
            capture_output=True,
            check=False,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"

    state = result.stdout.strip().splitlines()[0] if result.stdout.strip() else "unknown"
    # systemctl's textual state is useful and bounded; avoid copying arbitrary
    # stderr or command output into the administrative API.
    return state[:32] if state else "unknown"


def _collect_services() -> dict[str, str]:
    # As quatro consultas são independentes; em caso de D-Bus lento, o ciclo
    # fica limitado aproximadamente ao timeout de uma consulta, não à soma.
    with ThreadPoolExecutor(max_workers=len(SERVICE_UNITS), thread_name_prefix="service-probe") as executor:
        futures = {
            name: executor.submit(_service_state, unit)
            for name, unit in SERVICE_UNITS.items()
        }
        return {name: future.result() for name, future in futures.items()}


def _host_uptime() -> float | None:
    try:
        value = Path("/proc/uptime").read_text(encoding="utf-8").split()[0]
        return round(max(0.0, float(value)), 3)
    except (OSError, IndexError, ValueError):
        return None


def collect_snapshot(cpu_sampler: CpuSampler) -> dict[str, Any]:
    memory_total, memory_available, memory_used_percent = _collect_memory()
    disk_total, disk_used, disk_used_percent = _collect_disk()
    gpu_available, gpus = _collect_gpus()
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "collected_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "hostname": socket.gethostname()[:255],
        "host_uptime_seconds": _host_uptime(),
        "cpu_percent": cpu_sampler.sample(),
        "memory_total_bytes": memory_total,
        "memory_available_bytes": memory_available,
        "memory_used_percent": memory_used_percent,
        "disk_path": "/",
        "disk_total_bytes": disk_total,
        "disk_used_bytes": disk_used,
        "disk_used_percent": disk_used_percent,
        "gpu_available": gpu_available,
        "gpus": gpus,
        "services": _collect_services(),
    }


def write_snapshot(snapshot: dict[str, Any], output: Path) -> None:
    """Escreve o arquivo de forma atômica para o backend nunca ler parcial."""
    output = output.expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.",
        suffix=".tmp",
        dir=output.parent,
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(snapshot, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, output)
        try:
            directory_fd = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY)
        except OSError:
            directory_fd = None
        if directory_fd is not None:
            try:
                try:
                    os.fsync(directory_fd)
                except OSError as exc:
                    # O replace já tornou o snapshot visível; alguns FS não
                    # permitem fsync no diretório, então isso não deve perder
                    # o ciclo de coleta.
                    LOGGER.debug("não foi possível sincronizar diretório: %s", exc)
            finally:
                os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Arquivo JSON do snapshot")
    parser.add_argument(
        "--interval",
        type=float,
        default=30.0,
        help="Intervalo entre coletas, em segundos (padrão: 30)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Executa uma coleta e termina; útil para diagnóstico e testes",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.interval <= 0:
        raise SystemExit("--interval deve ser maior que zero")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    sampler = CpuSampler()
    # A primeira leitura de /proc/stat só estabelece a linha de base. O breve
    # aquecimento garante que o primeiro snapshot já contenha CPU, sem repetir
    # consultas de GPU ou de systemd.
    sampler.sample()
    time.sleep(min(CPU_WARMUP_SECONDS, max(0.1, args.interval)))
    while True:
        try:
            write_snapshot(collect_snapshot(sampler), args.output)
        except Exception:
            LOGGER.exception("falha ao atualizar snapshot de métricas")
            if args.once:
                return 1
        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
