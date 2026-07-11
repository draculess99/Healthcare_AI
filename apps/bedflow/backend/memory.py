"""Lightweight JSON memory for BedFlow AI's demonstration workflow."""

from __future__ import annotations

import datetime
import json
import os
import threading
from typing import Any

from .storage import runtime_json_path

STATE_PATH = runtime_json_path("bedflow_memory_state.json")
HISTORY_PATH = runtime_json_path("bedflow_memory_history.json", [])
_MEMORY_LOCK = threading.RLock()


def _default_state() -> dict[str, Any]:
    return {
        "recent_avg_discharge_delay_hours": 0.0,
        "recent_readmission_risk_trend": "stable",
        "most_common_bottleneck": "None",
        "recent_bed_recovery_count": 0,
        "last_recommendation": "None",
        "last_updated": str(datetime.datetime.now()),
        "memory_reasoning": "Initial state",
    }


def _atomic_write(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=4)
    os.replace(temp_path, path)


def init_memory() -> None:
    with _MEMORY_LOCK:
        if not os.path.exists(STATE_PATH):
            _atomic_write(STATE_PATH, _default_state())
        if not os.path.exists(HISTORY_PATH):
            _atomic_write(HISTORY_PATH, [])


def get_memory_state() -> dict[str, Any]:
    init_memory()
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else _default_state()
    except (OSError, json.JSONDecodeError):
        return _default_state()


def update_memory_state(updates: dict[str, Any]) -> dict[str, Any]:
    with _MEMORY_LOCK:
        state = get_memory_state()
        state.update(updates)
        state["last_updated"] = str(datetime.datetime.now())
        _atomic_write(STATE_PATH, state)
        return state


def append_memory_history(record: dict[str, Any]) -> None:
    with _MEMORY_LOCK:
        init_memory()
        item = dict(record)
        item["timestamp"] = str(datetime.datetime.now())
        try:
            with open(HISTORY_PATH, "r", encoding="utf-8") as handle:
                history = json.load(handle)
            if not isinstance(history, list):
                history = []
        except (OSError, json.JSONDecodeError):
            history = []
        history.append(item)
        _atomic_write(HISTORY_PATH, history)


def find_similar_bedflow_events(current_case: dict[str, Any], top_k: int = 3) -> list[dict[str, Any]]:
    init_memory()
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as handle:
            history = json.load(handle)
        if not isinstance(history, list):
            history = []
    except (OSError, json.JSONDecodeError):
        history = []

    if not history:
        return []

    scored_history: list[tuple[int, dict[str, Any]]] = []
    curr_sig = current_case.get("scenario_signature", {})

    for event in history:
        score = 0
        ev_sig = event.get("scenario_signature", {})
        if ev_sig.get("primary_bottleneck") == curr_sig.get("primary_bottleneck"):
            score += 3
        if ev_sig.get("readmission_risk_level") == curr_sig.get("readmission_risk_level"):
            score += 2
        if ev_sig.get("delay_risk_level") == curr_sig.get("delay_risk_level"):
            score += 2
        if ev_sig.get("discharge_destination") == curr_sig.get("discharge_destination"):
            score += 1
        scored_history.append((score, event))

    scored_history.sort(key=lambda item: item[0], reverse=True)
    return [event for score, event in scored_history[:top_k] if score > 0]
