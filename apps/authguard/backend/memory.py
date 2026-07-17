from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOCK = threading.RLock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JSONMemoryStore:
    """Small, transparent JSON persistence layer for a single-instance portfolio app."""

    def __init__(self, base_dir: str | Path | None = None) -> None:
        project_root = Path(__file__).resolve().parents[1]
        self.base_dir = Path(
            base_dir
            or os.getenv("AUTHGUARD_DATA_DIR")
            or (project_root / "database")
        )
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.files = {
            "cases": self.base_dir / "cases.json",
            "memory": self.base_dir / "memory_history.json",
            "audit": self.base_dir / "audit_log.json",
            "state": self.base_dir / "memory_state.json",
        }
        for key, path in self.files.items():
            default: Any = [] if key != "state" else {
                "schema_version": 1,
                "created_at": _utc_now(),
                "processed_cases": 0,
                "reviewed_cases": 0,
            }
            self._ensure(path, default)

    @staticmethod
    def _ensure(path: Path, default: Any) -> None:
        if not path.exists():
            path.write_text(json.dumps(default, indent=2), encoding="utf-8")

    @staticmethod
    def _read(path: Path, default: Any) -> Any:
        with _LOCK:
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return default

    @staticmethod
    def _write(path: Path, payload: Any) -> None:
        with _LOCK:
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
            tmp.replace(path)

    def list_cases(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._read(self.files["cases"], [])
        return list(reversed(rows[-limit:]))

    def get_case(self, run_id: str) -> dict[str, Any] | None:
        rows = self._read(self.files["cases"], [])
        for row in rows:
            if row.get("run_id") == run_id:
                return row
        return None


    def append_case(self, case_record: dict[str, Any]) -> None:
        rows = self._read(self.files["cases"], [])
        rows.append(case_record)
        self._write(self.files["cases"], rows[-1000:])
        state = self.get_state()
        state["processed_cases"] = int(state.get("processed_cases", 0)) + 1
        state["last_processed_at"] = _utc_now()
        self._write(self.files["state"], state)

    def append_memory(self, memory_record: dict[str, Any]) -> None:
        rows = self._read(self.files["memory"], [])
        rows.append(memory_record)
        self._write(self.files["memory"], rows[-1500:])

    def list_memory(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._read(self.files["memory"], [])
        return list(reversed(rows[-limit:]))

    def append_audit(self, audit_record: dict[str, Any]) -> None:
        rows = self._read(self.files["audit"], [])
        rows.append(audit_record)
        self._write(self.files["audit"], rows[-2000:])
        state = self.get_state()
        state["reviewed_cases"] = int(state.get("reviewed_cases", 0)) + 1
        state["last_reviewed_at"] = _utc_now()
        self._write(self.files["state"], state)

    def list_audit(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._read(self.files["audit"], [])
        return list(reversed(rows[-limit:]))

    def get_state(self) -> dict[str, Any]:
        return self._read(self.files["state"], {})

    def find_similar(self, case: dict[str, Any], limit: int = 3) -> list[dict[str, Any]]:
        rows = self._read(self.files["memory"], [])
        scored: list[tuple[int, dict[str, Any]]] = []
        for row in rows:
            score = 0
            if row.get("payer") == case.get("payer"):
                score += 3
            if row.get("service_type") == case.get("service_type"):
                score += 3
            if row.get("diagnosis_group") == case.get("diagnosis_group"):
                score += 2
            if bool(row.get("urgent")) == bool(case.get("urgent")):
                score += 1
            if row.get("decision") in {"HUMAN_REVIEW_REQUIRED", "HOLD_FOR_DOCUMENTATION"}:
                score += 1
            if score:
                scored.append((score, row))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [dict(row, similarity_score=score) for score, row in scored[:limit]]
