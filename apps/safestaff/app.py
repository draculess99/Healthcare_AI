import os
import sys
import time
import subprocess
import signal
from backend.model import train_model, CSV_PATH, MODEL_PATH

def main():
    print("=========================================================")
    print("   SafeStaff AI - 2-Tier Multi-Agent Staffing System     ")
    print("=========================================================")

    # 1. Train XGBoost Model on Startup if not trained
    if not os.path.exists(MODEL_PATH):
        print("Model file not found. Auto-generating data and training XGBoost...")
        train_model(CSV_PATH, MODEL_PATH)
    else:
        print("XGBoost model found. Skipping training.")

    # Prepare environment for backend
    backend_env = os.environ.copy()
    backend_env["PORT"] = "5000"

    # 2. Launch Flask Backend (Port 5000)
    print("\nStarting Flask API Backend on http://127.0.0.1:5000...")
    backend_proc = subprocess.Popen(
        [sys.executable, "-m", "backend.server"],
        env=backend_env
    )

    # 3. Wait for Flask to boot up
    time.sleep(2)

    # Prepare environment for frontend
    frontend_env = os.environ.copy()
    frontend_env["API_BASE_URL"] = "http://localhost:5000"
    
    railway_port = os.environ.get("PORT", "8501")

    # 4. Launch Streamlit Frontend Dashboard (Railway PORT)
    print(f"Starting Streamlit Dashboard on http://0.0.0.0:{railway_port}...")
    frontend_script = os.path.join("frontend", "dashboard.py")
    frontend_proc = subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run", frontend_script,
            "--server.address=0.0.0.0",
            f"--server.port={railway_port}"
        ],
        env=frontend_env
    )

    print("\nSafeStaff AI is running successfully!")
    print(f"To open the UI, navigate to http://localhost:{railway_port} in your browser.")
    print("Press Ctrl+C to terminate both servers.")
    print("=========================================================\n")

    # Keep script running and catch Ctrl+C to stop subprocesses
    try:
        while True:
            # Check if backend or frontend died
            if backend_proc.poll() is not None:
                print("Error: Flask Backend stopped unexpectedly.")
                break
            if frontend_proc.poll() is not None:
                print("Error: Streamlit Frontend stopped unexpectedly.")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutdown signal received. Stopping servers...")
    finally:
        # Terminate processes
        backend_proc.terminate()
        frontend_proc.terminate()
        
        # Wait for shutdown
        backend_proc.wait()
        frontend_proc.wait()
        print("Both servers shut down cleanly. Goodbye!")

if __name__ == "__main__":
    main()
