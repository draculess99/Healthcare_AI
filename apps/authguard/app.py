from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from dotenv import load_dotenv


def run_backend() -> None:
    from waitress import serve
    from backend.server import create_app

    port = int(os.getenv("AUTHGUARD_API_PORT", "5008"))
    serve(create_app(), host="0.0.0.0", port=port, threads=4)


def main() -> int:
    project_root = Path(__file__).resolve().parent
    os.chdir(project_root)
    load_dotenv(project_root / ".env")
    backend_thread = threading.Thread(target=run_backend, daemon=True, name="authguard-api")
    backend_thread.start()
    time.sleep(1.2)

    port = os.getenv("PORT", "8501")
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "frontend/dashboard.py",
        "--server.address=0.0.0.0",
        f"--server.port={port}",
        "--browser.gatherUsageStats=false",
    ]
    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main())
