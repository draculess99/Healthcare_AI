"""Runtime JSON storage configuration for BedFlow AI.

BedFlow AI intentionally keeps a lightweight JSON persistence layer for the
portfolio/demo deployment. Mutable JSON records can be redirected to a mounted
persistent directory with ``BEDFLOW_DATA_DIR`` while static datasets, model
artifacts, policies, and source code remain inside the application image.

Recommended Railway configuration::

    BEDFLOW_DATA_DIR=/data

Attach a Railway volume at ``/data``. On first startup, missing runtime files
are seeded from the packaged ``database`` directory when available, otherwise
safe empty/default payloads are created.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import threading
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGED_DATABASE_DIR = PROJECT_ROOT / "database"
RECOMMENDED_VOLUME_MOUNT = "/data"

_STORAGE_LOCK = threading.Lock()


def _default_memory_state() -> dict[str, Any]:
    return {
        "recent_avg_discharge_delay_hours": 0.0,
        "recent_readmission_risk_trend": "stable",
        "most_common_bottleneck": "None",
        "recent_bed_recovery_count": 0,
        "last_recommendation": "None",
        "last_updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "memory_reasoning": "Initial state",
    }


DEFAULT_RUNTIME_PAYLOADS: dict[str, Any | Callable[[], Any]] = {
    "tasks.json": [],
    "task_events.json": [],
    "audit_log.json": [],
    "simulation_runs.json": [],
    "access_log.json": [],
    "demo_users.json": [],
    "bedflow_memory_state.json": _default_memory_state,
    "bedflow_memory_history.json": [],
}


def runtime_data_dir() -> Path:
    """Return the configured mutable JSON directory as an absolute path.

    Local source runs retain the existing ``database`` directory by default.
    Container/Railway deployments should set ``BEDFLOW_DATA_DIR=/data`` and
    attach a persistent volume to that mount point.
    """
    configured = os.getenv("BEDFLOW_DATA_DIR", "").strip()
    if not configured:
        return PACKAGED_DATABASE_DIR.resolve()

    path = Path(configured).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _payload_for(filename: str, default: Any | Callable[[], Any] | None = None) -> Any:
    payload = DEFAULT_RUNTIME_PAYLOADS.get(filename, [] if default is None else default)
    if default is not None:
        payload = default
    return payload() if callable(payload) else payload


def _atomic_json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    os.replace(temp_path, path)


def runtime_json_path(
    filename: str,
    default: Any | Callable[[], Any] | None = None,
    *,
    seed_from_package: bool = True,
) -> str:
    """Resolve and initialize one mutable JSON file.

    When an external runtime directory is configured and empty, a packaged
    seed with the same filename is copied once. If no packaged seed exists, a
    safe default payload is created. Existing mounted data is never replaced.
    """
    safe_name = Path(filename).name
    target = runtime_data_dir() / safe_name

    with _STORAGE_LOCK:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            return str(target)

        source = PACKAGED_DATABASE_DIR / safe_name
        same_location = source.resolve() == target.resolve()
        if seed_from_package and source.exists() and not same_location:
            shutil.copy2(source, target)
        else:
            _atomic_json_write(target, _payload_for(safe_name, default))

    return str(target)


def initialize_runtime_storage() -> dict[str, Any]:
    """Create all known runtime JSON stores and return a storage summary."""
    files: dict[str, str] = {}
    for filename in DEFAULT_RUNTIME_PAYLOADS:
        files[filename] = runtime_json_path(filename)
    status = runtime_storage_status()
    status["files"] = files
    return status


def runtime_storage_status() -> dict[str, Any]:
    """Describe the configured JSON persistence mode for readiness/UI output."""
    configured = os.getenv("BEDFLOW_DATA_DIR", "").strip()
    directory = runtime_data_dir()
    external = directory != PACKAGED_DATABASE_DIR.resolve()
    return {
        "mode": "external-json-directory" if external else "project-local-json",
        "runtime_data_dir": str(directory),
        "bedflow_data_dir_configured": bool(configured),
        "external_runtime_directory": external,
        "recommended_railway_mount": RECOMMENDED_VOLUME_MOUNT,
        "database_engine": "JSON flat files",
        "single_instance_recommended": True,
        "note": (
            "Attach a persistent volume to this directory to preserve mutable records "
            "across redeployments. JSON remains intended for a single application instance."
        ),
    }
