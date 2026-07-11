# Deployment Guide: MedPack AI

MedPack AI is a two-service app:

1. **Backend service**: Flask API on `/health`, `/api/run-medpack-committee`, `/api/packing-queue`, etc.
2. **Frontend service**: Streamlit dashboard that calls the backend through `MEDPACK_API_BASE_URL`.

Do not deploy both services as one web process on Railway/Render unless you know how to run a process manager. The clean setup is one backend service and one frontend service.

---

## Railway Setup

### Backend service

**Start command:**

```bash
./start_backend.sh
```

Railway provides `PORT` automatically. The backend now binds to `0.0.0.0`, which is required for public hosting.

After deployment, test:

```text
https://YOUR-BACKEND-DOMAIN/health
```

Expected response:

```json
{"service":"MedPack AI backend","status":"ok"}
```

### Frontend service

**Start command:**

```bash
./start_frontend.sh
```

Set this environment variable on the frontend service:

```text
MEDPACK_API_BASE_URL=https://YOUR-BACKEND-DOMAIN
```

The frontend uses Streamlit and binds to `0.0.0.0:$PORT` for deployment.

---

## Local Development on Windows 11

Recommended one-click option from Command Prompt or File Explorer:

```bat
RUN_ME.bat
```

This installs dependencies and launches both services through `app.py`.

Separate-window option, useful when debugging backend and frontend independently:

```bat
RUN_BACKEND.bat
RUN_FRONTEND.bat
```

PowerShell alternatives are also included:

```powershell
.\RUN_BACKEND.ps1
.\RUN_FRONTEND.ps1
```

Run tests on Windows:

```bat
RUN_TESTS.bat
```

Manual Python option:

```bat
python -m pip install -r requirements.txt
python app.py
```

Local URLs:

```text
Backend:   http://127.0.0.1:5001/health
Dashboard: http://127.0.0.1:8502
```

---

## Smoke Tests

Windows:

```bat
RUN_TESTS.bat
```

Or manually:

```bat
python -m pytest
```

Manual backend test from Windows PowerShell:

```powershell
Invoke-RestMethod http://127.0.0.1:5001/health
Invoke-RestMethod "http://127.0.0.1:5001/api/packing-queue?limit=5"
```

---

## Important Environment Variables

| Variable | Service | Purpose |
|---|---|---|
| `PORT` | Backend/Frontend | Set automatically by Railway/Render |
| `MEDPACK_API_BASE_URL` | Frontend | Public backend URL |
| `MEDPACK_BACKEND_PORT` | Local backend | Optional local backend port override |
| `MEDPACK_FRONTEND_PORT` | Local frontend | Optional local frontend port override |
| `FLASK_DEBUG` | Backend | Set to `1` only for local debugging |

## Local vs Remote Switch

The Streamlit left sidebar now includes two runtime controls:

1. **Backend target**
   - `Local Backend` uses `http://127.0.0.1:5001` on your Windows 11 laptop.
   - `Remote Backend` lets you paste a deployed Railway/Render backend URL.

2. **Agent execution**
   - `Local AI Mode — zero tokens` is the safe default. It uses XGBoost, shortage rules, packing optimization, JSON memory, and deterministic local committee agents.
   - `Remote LLM Mode — may use tokens` only makes a remote LLM call if the backend has both `USE_LLM_AGENTS=true` and `GEMINI_API_KEY` configured.

Safe default:

```env
DEFAULT_AGENT_MODE=local
USE_LLM_AGENTS=false
```

That means you can demo the project locally without burning Gemini/OpenAI tokens.
