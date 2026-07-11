from __future__ import annotations

import json
from pathlib import Path

import backend.storage as storage


def test_external_runtime_directory_creates_safe_default(monkeypatch, tmp_path):
    runtime = tmp_path / "runtime"
    monkeypatch.setenv("BEDFLOW_DATA_DIR", str(runtime))
    path = Path(storage.runtime_json_path("custom.json", {"ready": True}, seed_from_package=False))
    assert path == runtime / "custom.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {"ready": True}


def test_packaged_seed_is_copied_once_and_existing_volume_data_is_preserved(monkeypatch, tmp_path):
    packaged = tmp_path / "packaged"
    runtime = tmp_path / "runtime"
    packaged.mkdir()
    (packaged / "tasks.json").write_text('[{"task_id":"SEED"}]', encoding="utf-8")
    monkeypatch.setattr(storage, "PACKAGED_DATABASE_DIR", packaged)
    monkeypatch.setenv("BEDFLOW_DATA_DIR", str(runtime))

    target = Path(storage.runtime_json_path("tasks.json", []))
    assert json.loads(target.read_text(encoding="utf-8"))[0]["task_id"] == "SEED"

    target.write_text('[{"task_id":"PERSISTED"}]', encoding="utf-8")
    storage.runtime_json_path("tasks.json", [])
    assert json.loads(target.read_text(encoding="utf-8"))[0]["task_id"] == "PERSISTED"


def test_initialize_runtime_storage_creates_all_mutable_stores(monkeypatch, tmp_path):
    packaged = tmp_path / "packaged"
    runtime = tmp_path / "runtime"
    packaged.mkdir()
    monkeypatch.setattr(storage, "PACKAGED_DATABASE_DIR", packaged)
    monkeypatch.setenv("BEDFLOW_DATA_DIR", str(runtime))

    status = storage.initialize_runtime_storage()
    assert status["mode"] == "external-json-directory"
    assert Path(status["runtime_data_dir"]) == runtime
    assert set(status["files"]) == set(storage.DEFAULT_RUNTIME_PAYLOADS)
    assert all(Path(path).exists() for path in status["files"].values())
    state = json.loads((runtime / "bedflow_memory_state.json").read_text(encoding="utf-8"))
    assert state["memory_reasoning"] == "Initial state"


def test_relative_data_directory_resolves_from_project_root(monkeypatch):
    monkeypatch.setenv("BEDFLOW_DATA_DIR", "data/runtime")
    expected = (storage.PROJECT_ROOT / "data" / "runtime").resolve()
    assert storage.runtime_data_dir() == expected
