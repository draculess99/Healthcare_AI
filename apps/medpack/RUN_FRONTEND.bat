@echo off
setlocal
cd /d "%~dp0"

echo ==========================================
echo   MedPack AI - Streamlit Frontend ^(Windows^)
echo ==========================================

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found on PATH. Install Python 3.11+ or enable "Add Python to PATH".
    pause
    exit /b 1
)

echo Installing dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo Dependency install failed.
    pause
    exit /b 1
)

echo Starting Streamlit dashboard on http://127.0.0.1:8503
set MEDPACK_API_BASE_URL=http://127.0.0.1:5001
python -m streamlit run frontend/dashboard.py --server.port 8503 --server.address 127.0.0.1 --server.headless true
pause
