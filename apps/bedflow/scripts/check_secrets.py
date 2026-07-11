#!/usr/bin/env python3
"""Fail CI when release content contains common secret files or key patterns."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


TEXT_SUFFIXES = {
    ".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".html", ".css", ".js", ".env", "",
}
SKIP_PARTS = {
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache", "dataset_diabetes", "models",
}
SECRET_PATTERNS = {
    "Groq key": re.compile(r"\bgsk_[A-Za-z0-9_-]{20,}\b"),
    "Google API key": re.compile(r"\bAIza[A-Za-z0-9_-]{30,}\b"),
    "OpenAI-style key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "Private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
}


def scan(root: Path) -> list[str]:
    findings: list[str] = []
    env_file = root / ".env"
    if env_file.exists():
        findings.append("Forbidden release file: .env")

    for path in root.rglob("*"):
        if not path.is_file() or any(part in SKIP_PARTS for part in path.parts):
            continue
        if path.name == ".env.example":
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"Dockerfile", "Procfile", "INFO"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{label} pattern found in {path.relative_to(root)}")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    findings = scan(root)
    if findings:
        print("Secret scan failed:")
        for finding in findings:
            print(f" - {finding}")
        return 1
    print("Secret scan passed: no forbidden .env file or common key pattern found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
