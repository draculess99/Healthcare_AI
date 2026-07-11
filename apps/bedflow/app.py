"""
BedFlow AI App Launcher

Run the full application with:

    python app.py

This launches:
1. Flask backend API
2. Streamlit frontend dashboard

It also generates the synthetic BedFlow dataset if it is missing.
"""

import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from backend.storage import initialize_runtime_storage


ROOT_DIR = Path(__file__).resolve().parent

DATASET_PATH = ROOT_DIR / "database" / "bedflow_patient_data.csv"
READMISSION_TRAINING_PATH = ROOT_DIR / "database" / "readmission_training_data.csv"
READMISSION_GENERATOR = ROOT_DIR / "scripts" / "prepare_diabetes_readmission_data.py"
DATA_GENERATOR = ROOT_DIR / "scripts" / "generate_bedflow_dataset.py"

BACKEND_MODULE = "backend.api"
DASHBOARD_PATH = ROOT_DIR / "frontend" / "dashboard.py"
BACKEND_HOST = os.getenv("BEDFLOW_API_HOST", "127.0.0.1")
BACKEND_PORT = int(os.getenv("BEDFLOW_API_PORT", "5005"))
DASHBOARD_PORT = int(os.getenv("PORT", os.getenv("BEDFLOW_DASHBOARD_PORT", "8501")))


def generate_dataset_if_missing() -> None:
    """Generate the synthetic BedFlow dataset if it does not exist."""
    if DATASET_PATH.exists():
        print(f"✅ Dataset found: {DATASET_PATH}")
        return

    print("⚠️ Dataset not found. Generating synthetic BedFlow dataset...")

    if not DATA_GENERATOR.exists():
        raise FileNotFoundError(f"Dataset generator not found: {DATA_GENERATOR}")

    subprocess.run(
        [sys.executable, str(DATA_GENERATOR)],
        cwd=str(ROOT_DIR),
        check=True,
    )

    if not DATASET_PATH.exists():
        raise RuntimeError("Dataset generation ran, but dataset file was not created.")

    print(f"✅ Dataset generated: {DATASET_PATH}")


def generate_readmission_dataset_if_missing() -> None:
    """Prepare the Stage 6 public readmission training layer if it is missing."""
    if READMISSION_TRAINING_PATH.exists():
        print(f"✅ Public readmission training dataset found: {READMISSION_TRAINING_PATH}")
        return

    if not READMISSION_GENERATOR.exists():
        print("⚠️ Stage 6 readmission generator not found; readmission model can fall back to synthetic data.")
        return

    print("⚠️ Public readmission training dataset not found. Preparing Stage 6 data layer...")
    subprocess.run(
        [sys.executable, str(READMISSION_GENERATOR)],
        cwd=str(ROOT_DIR),
        check=True,
    )

    if READMISSION_TRAINING_PATH.exists():
        print(f"✅ Public readmission training dataset prepared: {READMISSION_TRAINING_PATH}")
    else:
        print("⚠️ Public readmission dataset was not created; app can still run in synthetic-only fallback mode.")


def start_backend() -> subprocess.Popen:
    """Start the backend with Waitress when available, otherwise Flask."""
    print(f"🚀 Starting backend at http://{BACKEND_HOST}:{BACKEND_PORT} ...")

    use_waitress = os.getenv("BEDFLOW_USE_WAITRESS", "true").lower() != "false"
    if use_waitress and importlib.util.find_spec("waitress") is not None:
        command = [
            sys.executable,
            "-m",
            "waitress",
            "--host",
            BACKEND_HOST,
            "--port",
            str(BACKEND_PORT),
            "--threads=2",  # Reduce threads to save memory
            "backend.api:app",
        ]
    else:
        command = [sys.executable, "-m", BACKEND_MODULE]

    env = os.environ.copy()
    env["BEDFLOW_API_HOST"] = BACKEND_HOST
    env["BEDFLOW_API_PORT"] = str(BACKEND_PORT)
    env.setdefault("MALLOC_ARENA_MAX", "2")  # Crucial to prevent Python glibc memory fragmentation bloat
    return subprocess.Popen(command, cwd=str(ROOT_DIR), env=env)


def start_frontend() -> subprocess.Popen:
    """Start Streamlit on the local or platform-provided public port."""
    print(f"🚀 Starting Streamlit dashboard at http://localhost:{DASHBOARD_PORT} ...")

    env = os.environ.copy()
    env.setdefault("BEDFLOW_API_URL", f"http://{BACKEND_HOST}:{BACKEND_PORT}/api")
    env.setdefault("MALLOC_ARENA_MAX", "2")  # Memory optimization
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(DASHBOARD_PATH),
            "--server.address=0.0.0.0",
            f"--server.port={DASHBOARD_PORT}",
            "--server.fileWatcherType=none",      # Disable file watcher (saves ~50-100MB RAM)
            "--browser.gatherUsageStats=false",   # Disable telemetry
            "--global.developmentMode=false"      # Disable dev-mode overhead
        ],
        cwd=str(ROOT_DIR),
        env=env,
    )


def stop_process(process: subprocess.Popen | None, name: str) -> None:
    """Gracefully stop a child process."""
    if process is None:
        return

    if process.poll() is not None:
        return

    print(f"🛑 Stopping {name}...")

    try:
        process.terminate()
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        print(f"⚠️ {name} did not stop gracefully. Killing it...")
        process.kill()
    except Exception as exc:
        print(f"⚠️ Could not stop {name}: {exc}")


def main() -> None:
    backend_process = None
    frontend_process = None

    print("=" * 72)
    print("🏥 BedFlow AI")
    print("Agentic Discharge Planning and Readmission Risk Decision Support")
    print("=" * 72)

    try:
        storage = initialize_runtime_storage()
        print(f"✅ Runtime JSON storage: {storage['runtime_data_dir']} ({storage['mode']})")
        generate_dataset_if_missing()
        generate_readmission_dataset_if_missing()

        backend_process = start_backend()

        # Give Flask a few seconds to start before Streamlit calls the API.
        time.sleep(4)

        frontend_process = start_frontend()

        print("\n✅ BedFlow AI is starting.")
        print(f"Backend:   http://{BACKEND_HOST}:{BACKEND_PORT}")
        print(f"Dashboard: http://localhost:{DASHBOARD_PORT}")
        print("\nPress Ctrl+C to stop both services.\n")

        while True:
            if backend_process.poll() is not None:
                print("❌ Flask backend stopped unexpectedly.")
                break

            if frontend_process.poll() is not None:
                print("❌ Streamlit dashboard stopped unexpectedly.")
                break

            time.sleep(2)

    except KeyboardInterrupt:
        print("\n🛑 Ctrl+C received. Shutting down BedFlow AI...")

    except Exception as exc:
        print(f"\n❌ Launcher error: {exc}")

    finally:
        stop_process(frontend_process, "Streamlit dashboard")
        stop_process(backend_process, "Flask backend")
        print("✅ BedFlow AI stopped.")


if __name__ == "__main__":
    main()