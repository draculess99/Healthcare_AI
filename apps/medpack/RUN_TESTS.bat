@echo off
setlocal
cd /d "%~dp0"

echo ==========================================
echo   MedPack AI - Tests ^(Windows^)
echo ==========================================

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found on PATH. Install Python 3.11+ or enable "Add Python to PATH".
    pause
    exit /b 1
)

python -m pip install -r requirements.txt
if errorlevel 1 (
    echo Dependency install failed.
    pause
    exit /b 1
)

python -m pytest
pause
