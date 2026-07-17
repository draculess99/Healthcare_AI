# Healthcare AI Control Tower — One Railway Service

This repository combines five healthcare decision-support applications into one Railway service and one public domain:

- `/safestaff/` — SafeStaff AI
- `/medpack/` — MedPack AI
- `/triage/` — Triage Assist AI
- `/bedflow/` — BedFlow AI
- `/authguard/` — AuthGuard AI (prior authorization / OffGuard module)
- `/` — unified portfolio/control-tower landing page
- `/health` — Railway health check

## Architecture

Railway exposes one public `$PORT`. Nginx listens on that port and routes each URL path to an internal Streamlit process. Each Streamlit dashboard talks to its own internal Flask API. All processes run inside one Railway service/container.

```text
Browser
  |
  v
Nginx :$PORT
  |-- /safestaff/ --> Streamlit :8601 --> Flask :5101
  |-- /medpack/   --> Streamlit :8602 --> Flask :5102
  |-- /triage/    --> Streamlit :8603 --> Flask :5103
  |-- /bedflow/   --> Streamlit :8604 --> Flask :5104
  `-- /authguard/ --> Streamlit :8605 --> Flask :5105
```

## Railway deployment

1. Create a new GitHub repository and upload the contents of this folder.
2. In Railway, choose **New Project → Deploy from GitHub Repo**.
3. Select this repository. Railway will detect the included `Dockerfile` and `railway.toml`.
4. Add any optional API-key variables used by the apps:
   - `GROQ_API_KEY`
   - `GOOGLE_API_KEY` or `GEMINI_API_KEY` for Gemini-enabled modules
   - `AUTHGUARD_DATA_DIR` only when mounting a persistent volume for AuthGuard JSON history
5. Deploy. Do not create five Railway services; this repository is designed to be one service.
6. Generate a Railway domain. The home page appears at the root URL.

The health check is configured as `/health` with a 120-second startup allowance because the machine-learning libraries and five dashboards may need time to initialize.

## Local Docker test

```bash
docker build -t healthcare-ai-control-tower .
docker run --rm -p 8080:8080 -e PORT=8080 healthcare-ai-control-tower
```

Then open `http://localhost:8080`.

## Resource warning

This is one billable Railway service, but it still runs ten Python application processes plus Nginx. Consolidation removes the overhead of five separately provisioned services, domains, and containers; it does not make the five applications consume the memory of only one application. ChromaDB, sentence-transformers, FAISS, XGBoost, and five Streamlit runtimes can require substantial RAM.

For the lowest cost, keep LLM agents optional, avoid retraining on startup, and consider removing unused local embedding models or large duplicated datasets after confirming each page works.

## Important files

- `start.sh` — starts all APIs, dashboards, and Nginx
- `nginx/default.conf.template` — path routing and WebSocket support
- `portal/index.html` — unified landing page
- `Dockerfile` — Railway container build
- `railway.toml` — Railway build, start, restart, and health-check settings
- `apps/` — the five embedded projects, kept in separate directories to avoid Python import collisions

## Persistence

Railway container files are normally ephemeral across redeployments. JSON logs, queues, approvals, and memory files that must survive redeployment should eventually be moved to a Railway Volume or database. The current package preserves the original file-based behavior.
"# Healthcare_AI" 
