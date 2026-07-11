@echo off
echo Starting Triage Assist AI...

echo Starting Backend (Flask)...
start "Triage Backend" cmd /k ".\venv\Scripts\activate & python backend\app.py"

timeout /t 2 /nobreak > NUL

echo Starting Frontend (Streamlit)...
start "Triage Frontend" cmd /k ".\venv\Scripts\activate & streamlit run frontend\app.py"
