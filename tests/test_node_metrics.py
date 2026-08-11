"""Testes do contrato do snapshot local de métricas."""

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from deploy.node_metrics import procelbot_node_metrics as collector
from app.core.config import settings
from app.services.node_metrics import read_node_metrics


def _snapshot(collected_at: datetime) -> dict:
    return {
        "schema_version": 1,
        "collected_at": collected_at.isoformat().replace("+00:00", "Z"),
        "hostname": "rtx-test",
        "host_uptime_seconds": 123.4,
        "cpu_percent": 12.5,
        "memory_total_bytes": 16 * 1024**3,
        "memory_available_bytes": 8 * 1024**3,
        "memory_used_percent": 50.0,
        "disk_path": "/",
        "disk_total_bytes": 100 * 1024**3,
        "disk_used_bytes": 20 * 1024**3,
        "disk_used_percent": 20.0,
        "gpu_available": True,
        "gpus": [
            {
                "index": 0,
                "name": "NVIDIA GeForce RTX 5090",
                "utilization_percent": 1.0,
                "memory_used_bytes": 512 * 1024**2,
                "memory_total_bytes": 32 * 1024**3,
                "temperature_c": 42.0,
                "power_w": 80.0,
            }
        ],
        "services": {"docker": "active", "backend": "active"},
    }


def test_read_node_metrics_validates_fresh_snapshot(tmp_path, monkeypatch):
    path = tmp_path / "latest.json"
    path.write_text(json.dumps(_snapshot(datetime.now(timezone.utc))), encoding="utf-8")
    monkeypatch.setattr(settings, "node_metrics_max_age_seconds", 60)

    result = read_node_metrics(str(path))

    assert result is not None
    assert result.fresh is True
    assert result.gpus[0].name == "NVIDIA GeForce RTX 5090"
    assert result.age_seconds >= 0


def test_read_node_metrics_returns_none_for_missing_or_invalid_snapshot(tmp_path):
    missing = read_node_metrics(str(tmp_path / "missing.json"))
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text("not-json", encoding="utf-8")
    invalid = read_node_metrics(str(invalid_path))

    assert missing is None
    assert invalid is None


def test_read_node_metrics_rejects_oversized_and_symlink_snapshots(tmp_path):
    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b"{" + b"a" * (128 * 1024) + b"}")
    target = tmp_path / "target.json"
    target.write_text(json.dumps(_snapshot(datetime.now(timezone.utc))), encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(target)

    assert read_node_metrics(str(oversized)) is None
    assert read_node_metrics(str(link)) is None


def test_read_node_metrics_marks_stale_snapshot_without_failing(tmp_path, monkeypatch):
    path = tmp_path / "latest.json"
    stale_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    path.write_text(json.dumps(_snapshot(stale_at)), encoding="utf-8")
    monkeypatch.setattr(settings, "node_metrics_max_age_seconds", 60)

    result = read_node_metrics(str(path))

    assert result is not None
    assert result.fresh is False
    assert result.age_seconds >= 300


def test_read_node_metrics_rejects_future_timestamp_as_fresh(tmp_path, monkeypatch):
    path = tmp_path / "latest.json"
    future_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    path.write_text(json.dumps(_snapshot(future_at)), encoding="utf-8")
    monkeypatch.setattr(settings, "node_metrics_max_age_seconds", 60)

    result = read_node_metrics(str(path))

    assert result is not None
    assert result.age_seconds == 0
    assert result.fresh is False
    assert result.clock_skew is True


def test_collect_gpus_degrades_when_nvidia_smi_fails(monkeypatch):
    class FailedCommand:
        returncode = 1
        stdout = ""

    monkeypatch.setattr(collector.shutil, "which", lambda _name: "/usr/bin/nvidia-smi")
    monkeypatch.setattr(collector.subprocess, "run", lambda *_args, **_kwargs: FailedCommand())

    gpu_available, gpus = collector._collect_gpus()

    assert gpu_available is False
    assert gpus == []


def test_collector_once_writes_schema_one_snapshot(tmp_path):
    script = Path(__file__).parents[1] / "deploy/node_metrics/procelbot_node_metrics.py"
    output = tmp_path / "latest.json"

    completed = subprocess.run(
        [sys.executable, str(script), "--output", str(output), "--once"],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["cpu_percent"] is not None
