import subprocess
import sys
import os
import time
import signal
import atexit

processes = []

def cleanup():
    print("Stopping Healthcare AI Control Tower...")
    for p in processes:
        if p.poll() is None:
            try:
                p.terminate()
            except Exception:
                pass

atexit.register(cleanup)

def run_bg(name, directory, env_vars, cmd):
    print(f"Starting {name}...")
    env = os.environ.copy()
    env.update(env_vars)
    # Ensure PYTHONPATH is set for streamlit apps
    if 'PYTHONPATH' not in env:
        env['PYTHONPATH'] = '.'
    else:
        env['PYTHONPATH'] = '.' + os.pathsep + env['PYTHONPATH']
        
    p = subprocess.Popen(
        cmd,
        cwd=directory,
        env=env,
        shell=False
    )
    processes.append(p)

def main():
    base_dir = os.path.abspath(os.path.dirname(__file__))
    
    # Common Streamlit args
    common_st = [
        "--server.address=127.0.0.1",
        "--server.headless=true",
        "--server.fileWatcherType=none",
        "--browser.gatherUsageStats=false"
    ]

    bedflow_data_dir = os.path.join(base_dir, "temp_data", "bedflow-data")
    os.makedirs(bedflow_data_dir, exist_ok=True)

    # 2. MedPack API
    run_bg(
        "MedPack API",
        os.path.join(base_dir, "apps", "medpack"),
        {
            "MEDPACK_BACKEND_PORT": "5102", 
            "PORT": "5102", 
            "MEDPACK_FORCE_LOCAL_COMMITTEE": "true",
            "MEDPACK_ALLOW_FULL_COMMITTEE_ROUTE": "false",
            "MEDPACK_ALLOW_COMMITTEE_STREAM": "false",
            "USE_LLM_AGENTS": "false",
            "DEFAULT_AGENT_MODE": "local"
        },
        [sys.executable, "-m", "backend.run_api"]
    )

    # 3. Triage API
    run_bg(
        "Triage API",
        os.path.join(base_dir, "apps", "triage"),
        {"TRIAGE_API_HOST": "127.0.0.1", "TRIAGE_API_PORT": "5103"},
        [sys.executable, "backend/app.py"]
    )

    # 4. BedFlow API
    run_bg(
        "BedFlow API",
        os.path.join(base_dir, "apps", "bedflow"),
        {"BEDFLOW_API_HOST": "127.0.0.1", "BEDFLOW_API_PORT": "5104", "BEDFLOW_DATA_DIR": bedflow_data_dir},
        [sys.executable, "-m", "backend.api"]
    )

    time.sleep(5)

    # 7. MedPack Streamlit
    run_bg(
        "MedPack page",
        os.path.join(base_dir, "apps", "medpack"),
        {
            "MEDPACK_API_BASE_URL": "http://127.0.0.1:5102",
            "MEDPACK_LOCAL_API_BASE_URL": "http://127.0.0.1:5102"
        },
        [sys.executable, "-m", "streamlit", "run", "frontend/dashboard.py", "--server.port=8602", "--server.baseUrlPath=medpack"] + common_st
    )

    # 8. Triage Streamlit
    run_bg(
        "Triage page",
        os.path.join(base_dir, "apps", "triage"),
        {"TRIAGE_API_URL": "http://127.0.0.1:5103/api"},
        [sys.executable, "-m", "streamlit", "run", "frontend/app.py", "--server.port=8603", "--server.baseUrlPath=triage"] + common_st
    )

    # 9. BedFlow Streamlit
    run_bg(
        "BedFlow page",
        os.path.join(base_dir, "apps", "bedflow"),
        {"BEDFLOW_API_URL": "http://127.0.0.1:5104/api", "BEDFLOW_DATA_DIR": bedflow_data_dir},
        [sys.executable, "-m", "streamlit", "run", "frontend/dashboard.py", "--server.port=8604", "--server.baseUrlPath=bedflow"] + common_st
    )

    print("\nAll services started!")
    print("You can access the applications locally at:")
    print(" - MedPack:   http://127.0.0.1:8602/medpack")
    print(" - Triage:    http://127.0.0.1:8603/triage")
    print(" - BedFlow:   http://127.0.0.1:8604/bedflow")
    print("\nPress Ctrl+C to stop all services.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
