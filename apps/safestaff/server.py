"""Railway/Gunicorn entrypoint for the SafeStaff AI backend.

Use: gunicorn server:app --bind 0.0.0.0:$PORT
"""
from backend.server import app
