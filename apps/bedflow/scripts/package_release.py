#!/usr/bin/env python3
"""Create a clean BedFlow AI release zip without secrets or runtime residue."""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path


EXCLUDED_PARTS = {
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "dist", "data",
}
EXCLUDED_NAMES = {
    ".env", ".DS_Store", "Thumbs.db", "demo_users.json", "access_log.json",
    "audit_log.json", "tasks.json", "task_events.json", "simulation_runs.json",
    "bedflow_memory_history.json", "bedflow_memory_state.json",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".log"}


def should_include(relative: Path) -> bool:
    if any(part in EXCLUDED_PARTS for part in relative.parts):
        return False
    if relative.name in EXCLUDED_NAMES:
        return False
    if relative.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    return True


def build_zip(root: Path, output: Path) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(root)
            if not should_include(relative):
                continue
            archive.write(path, Path(root.name) / relative)
            count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default="dist/bedflow_ai_release.zip")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    output = Path(args.output).resolve()
    count = build_zip(root, output)
    print(f"Created {output} with {count} files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
