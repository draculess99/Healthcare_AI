#!/usr/bin/env bash
set -Eeuo pipefail

export PORT="${PORT:-8080}"
export MALLOC_ARENA_MAX="${MALLOC_ARENA_MAX:-2}"

PIDS=()
cleanup() {
  echo "Stopping healthcare control tower..."
  for pid in "${PIDS[@]:-}"; do kill -TERM "$pid" 2>/dev/null || true; done
  wait || true
}
trap cleanup EXIT INT TERM

run_bg() {
  local name="$1" dir="$2"; shift 2
  echo "Starting $name..."
  (cd "$dir" && exec "$@") &
  PIDS+=("$!")
}

# Internal APIs
run_bg "SafeStaff API" /app/apps/safestaff env PORT=5101 HOST=127.0.0.1 FLASK_DEBUG=false python -m backend.server
run_bg "MedPack API" /app/apps/medpack env MEDPACK_BACKEND_PORT=5102 PORT=5102 MEDPACK_FORCE_LOCAL_COMMITTEE=true MEDPACK_ALLOW_FULL_COMMITTEE_ROUTE=false MEDPACK_ALLOW_COMMITTEE_STREAM=false USE_LLM_AGENTS=false DEFAULT_AGENT_MODE=local python -m backend.server
run_bg "Triage API" /app/apps/triage env TRIAGE_API_HOST=127.0.0.1 TRIAGE_API_PORT=5103 python backend/app.py
run_bg "BedFlow API" /app/apps/bedflow env BEDFLOW_API_HOST=127.0.0.1 BEDFLOW_API_PORT=5104 BEDFLOW_DATA_DIR=/tmp/bedflow-data python -m backend.api

sleep 5

# Four Streamlit applications, routed as pages under one public domain.
COMMON_ST=(--server.address=127.0.0.1 --server.headless=true --server.fileWatcherType=none --browser.gatherUsageStats=false)
run_bg "SafeStaff page" /app/apps/safestaff env API_BASE_URL=http://127.0.0.1:5101 streamlit run frontend/dashboard.py --server.port=8601 --server.baseUrlPath=safestaff "${COMMON_ST[@]}"
run_bg "MedPack page" /app/apps/medpack env MEDPACK_API_BASE_URL=http://127.0.0.1:5102 MEDPACK_LOCAL_API_BASE_URL=http://127.0.0.1:5102 streamlit run frontend/dashboard.py --server.port=8602 --server.baseUrlPath=medpack "${COMMON_ST[@]}"
run_bg "Triage page" /app/apps/triage env TRIAGE_API_URL=http://127.0.0.1:5103/api streamlit run frontend/app.py --server.port=8603 --server.baseUrlPath=triage "${COMMON_ST[@]}"
run_bg "BedFlow page" /app/apps/bedflow env BEDFLOW_API_URL=http://127.0.0.1:5104/api BEDFLOW_DATA_DIR=/tmp/bedflow-data streamlit run frontend/dashboard.py --server.port=8604 --server.baseUrlPath=bedflow "${COMMON_ST[@]}"

# Render Railway's dynamic public port into nginx config.
envsubst '${PORT}' < /app/nginx/default.conf.template > /etc/nginx/conf.d/default.conf
rm -f /etc/nginx/sites-enabled/default
nginx -g 'daemon off;' &
PIDS+=("$!")

echo "Healthcare AI Control Tower is available on port ${PORT}."

# Wait for all background processes to finish instead of exiting on the first failure.
wait
