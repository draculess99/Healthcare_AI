#!/bin/bash
# start.sh
# This script boots both the backend and frontend in a single container.

echo "Starting Flask backend..."
# Launch Flask in the background on the internal port 5000
python backend/app.py &

# Give the backend a few seconds to fully initialize
sleep 3

echo "Starting Streamlit frontend..."
# Launch Streamlit in the foreground, binding to Railway's dynamic $PORT
streamlit run frontend/app.py --server.port $PORT --server.address 0.0.0.0
