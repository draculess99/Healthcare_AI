FROM python:3.11-slim

WORKDIR /app

ENV PYTHONPATH=/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY frontend ./frontend
COPY backend ./backend
COPY database ./database

EXPOSE 8501

CMD streamlit run frontend/dashboard.py --server.address=0.0.0.0 --server.port=${PORT:-8501}
