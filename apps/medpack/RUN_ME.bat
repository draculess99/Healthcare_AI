@echo off
setlocal
cd /d "%~dp0"

echo ==========================================
echo   MedPack AI - One Click Local Run
echo   Windows 11 launcher
echo ==========================================

echo This starts BOTH backend and frontend from app.py.
echo Backend:   http://127.0.0.1:5001/health
echo Dashboard: http://127.0.0.1:8503
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found on PATH. Install Python 3.11+ or enable "Add Python to PATH".
    pause
    exit /b 1
)

echo Installing dependencies from requirements.txt...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo Error installing dependencies. Make sure Python and pip are on PATH.
    pause
    exit /b %errorlevel%
)

echo Launching MedPack AI...
python app.py
pause
