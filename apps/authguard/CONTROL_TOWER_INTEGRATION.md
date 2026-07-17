# AuthGuard AI control-tower integration

This application is embedded as the fifth module in Healthcare AI Control Tower.

- Public dashboard route: `/authguard/`
- Internal Streamlit port: `8605`
- Internal Flask API port: `5105`
- Runtime JSON directory: `AUTHGUARD_DATA_DIR` (defaults to `/tmp/authguard-data` in Docker)
- The control tower root `start.sh`, Nginx configuration, and root `requirements.txt` manage deployment.
