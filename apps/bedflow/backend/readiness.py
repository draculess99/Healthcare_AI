"""Stage 10A readiness and deployment checks for BedFlow AI."""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
from typing import Any

from .auth import AUTH_SECRET, DEFAULT_AUTH_SECRET, auth_status
from .models import (
    DATA_PATH,
    FEATURE_COLUMNS_ARTIFACT_PATH,
    MODEL_ARTIFACT_PATHS,
    bedflow_models,
)
from .observability import APP_VERSION, UPGRADE_STAGE
from .storage import runtime_storage_status


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _check(name: str, ok: bool, detail: str, critical: bool = True) -> dict[str, Any]:
    return {
        "name": name,
        "status": "pass" if ok else ("fail" if critical else "warning"),
        "critical": critical,
        "detail": detail,
    }


def _writable_directory(path: Path) -> tuple[bool, str]:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".bedflow-write-check"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True, f"Writable directory: {path}"
    except OSError as exc:
        return False, f"Directory is not writable: {path} ({exc})"


def build_readiness_report() -> dict[str, Any]:
    """Return deployment readiness without modifying models or patient records."""
    checks: list[dict[str, Any]] = []

    dataset_ok = Path(DATA_PATH).exists() and Path(DATA_PATH).is_file()
    checks.append(_check("patient_dataset", dataset_ok, f"Dataset path: {DATA_PATH}"))

    artifact_paths = [*MODEL_ARTIFACT_PATHS.values(), FEATURE_COLUMNS_ARTIFACT_PATH]
    missing = [path for path in artifact_paths if not Path(path).exists()]
    checks.append(
        _check(
            "model_artifacts",
            not missing,
            "All required saved artifacts are present."
            if not missing
            else f"Missing artifacts: {', '.join(missing)}",
        )
    )
    checks.append(
        _check(
            "models_loaded",
            bool(bedflow_models.is_trained),
            f"Active model version: {bedflow_models.model_version or 'not loaded'}",
        )
    )

    storage = runtime_storage_status()
    runtime_directory = Path(storage["runtime_data_dir"])
    writable, writable_detail = _writable_directory(runtime_directory)
    checks.append(
        _check(
            "runtime_storage",
            writable,
            f"{writable_detail}; mode={storage['mode']}",
        )
    )

    strong_secret = bool(AUTH_SECRET and AUTH_SECRET != DEFAULT_AUTH_SECRET and len(AUTH_SECRET) >= 24)
    require_strong = os.getenv("BEDFLOW_REQUIRE_STRONG_SECRETS", "false").lower() == "true"
    checks.append(
        _check(
            "authentication_secret",
            strong_secret,
            "A non-default authentication secret is configured."
            if strong_secret
            else "Using the local demonstration authentication secret; set BEDFLOW_AUTH_SECRET before public deployment.",
            critical=require_strong,
        )
    )

    persistence_detail = (
        f"Mutable JSON stores use {storage['runtime_data_dir']}. "
        + (
            "An external runtime directory is configured; attach a persistent volume at that path "
            "to preserve records across restarts and redeployments."
            if storage["external_runtime_directory"]
            else "Set BEDFLOW_DATA_DIR=/data and attach a Railway volume to preserve records across redeployments."
        )
        + " JSON mode is intended for one application instance rather than concurrent replicas."
    )
    checks.append(
        _check(
            "persistence_mode",
            False,
            persistence_detail,
            critical=False,
        )
    )

    failed_critical = [item for item in checks if item["critical"] and item["status"] == "fail"]
    warnings = [item for item in checks if item["status"] == "warning"]
    ready = not failed_critical
    status = "ready" if ready and not warnings else ("degraded" if ready else "unready")

    return {
        "status": status,
        "ready": ready,
        "app": "BedFlow AI",
        "app_version": APP_VERSION,
        "upgrade_stage": UPGRADE_STAGE,
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "model_version": bedflow_models.model_version,
        "authentication": auth_status(),
        "storage": storage,
        "checks": checks,
        "summary": {
            "passed": sum(item["status"] == "pass" for item in checks),
            "warnings": len(warnings),
            "failed": len(failed_critical),
        },
    }
