# MedPack AI - Windows 11 Quick Start

Use these files from the project root folder.

## Option 1: One-click local run

Double-click:

```bat
RUN_ME.bat
```

This will:

1. Install Python dependencies from `requirements.txt`.
2. Prepare data/model files if needed.
3. Start the Flask backend.
4. Start the Streamlit dashboard.

Open:

```text
http://127.0.0.1:8502
```

Backend health check:

```text
http://127.0.0.1:5001/health
```

## Option 2: Debug with two windows

Open Command Prompt in the project folder.

Window 1:

```bat
RUN_BACKEND.bat
```

Window 2:

```bat
RUN_FRONTEND.bat
```

This is better when you want to see backend errors separately from frontend errors.

## Run tests

```bat
RUN_TESTS.bat
```

## PowerShell alternatives

```powershell
.\RUN_BACKEND.ps1
.\RUN_FRONTEND.ps1
```

The `.sh` files are only for Linux/macOS/cloud deploy environments. On Windows 11, use the `.bat` or `.ps1` files.

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
