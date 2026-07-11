"""Stage 10A request observability for BedFlow AI.

This module provides lightweight, dependency-free production diagnostics:
structured request logs, request IDs, response timing, security headers, and
an in-process metrics snapshot. The metrics reset when the API process restarts;
production deployments should forward logs and metrics to a managed platform.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import threading
import time
import uuid
from collections import Counter
from typing import Any

from flask import Flask, g, jsonify, request
from werkzeug.exceptions import HTTPException


APP_VERSION = "10.2.0-persistent-json"
UPGRADE_STAGE = "10A"


class JsonFormatter(logging.Formatter):
    """Render structured log records as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in (
            "event_type",
            "request_id",
            "method",
            "path",
            "endpoint",
            "status_code",
            "latency_ms",
            "remote_addr",
            "user_id",
            "role",
            "error_type",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


class RequestMetrics:
    """Thread-safe in-process request counters for operational diagnostics."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with getattr(self, "_lock", threading.Lock()):
            self.started_at_utc = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            self.total_requests = 0
            self.total_errors = 0
            self.total_latency_ms = 0.0
            self.max_latency_ms = 0.0
            self.status_counts: Counter[str] = Counter()
            self.endpoint_counts: Counter[str] = Counter()
            self.last_error: dict[str, Any] | None = None

    def record(self, endpoint: str, status_code: int, latency_ms: float) -> None:
        with self._lock:
            self.total_requests += 1
            self.total_latency_ms += max(0.0, float(latency_ms))
            self.max_latency_ms = max(self.max_latency_ms, float(latency_ms))
            self.status_counts[str(status_code)] += 1
            self.endpoint_counts[str(endpoint or "unknown")] += 1
            if status_code >= 500:
                self.total_errors += 1

    def record_error(self, request_id: str, path: str, error: BaseException) -> None:
        with self._lock:
            self.last_error = {
                "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "request_id": request_id,
                "path": path,
                "error_type": type(error).__name__,
                "message": str(error)[:500],
            }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            average = self.total_latency_ms / self.total_requests if self.total_requests else 0.0
            return {
                "status": "success",
                "metrics_scope": "in-process; resets when the API process restarts",
                "started_at_utc": self.started_at_utc,
                "total_requests": self.total_requests,
                "total_server_errors": self.total_errors,
                "average_latency_ms": round(average, 2),
                "max_latency_ms": round(self.max_latency_ms, 2),
                "status_counts": dict(self.status_counts),
                "endpoint_counts": dict(self.endpoint_counts.most_common(30)),
                "last_error": dict(self.last_error) if self.last_error else None,
            }


REQUEST_METRICS = RequestMetrics()
LOGGER = logging.getLogger("bedflow.api")


def configure_logging() -> logging.Logger:
    """Configure the BedFlow logger once using text or JSON output."""
    level_name = os.getenv("BEDFLOW_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    output_format = os.getenv("BEDFLOW_LOG_FORMAT", "json").strip().lower()

    LOGGER.setLevel(level)
    LOGGER.propagate = False
    if not LOGGER.handlers:
        handler = logging.StreamHandler()
        if output_format == "json":
            handler.setFormatter(JsonFormatter())
        else:
            handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
            )
        LOGGER.addHandler(handler)
    return LOGGER


def _request_user() -> dict[str, Any]:
    user = getattr(g, "bedflow_user", None)
    return user if isinstance(user, dict) else {}


def configure_observability(app: Flask) -> None:
    """Attach request tracing, metrics, headers, and JSON error responses."""
    configure_logging()

    @app.before_request
    def _before_request() -> None:
        incoming = str(request.headers.get("X-Request-ID", "")).strip()
        g.request_id = incoming[:128] if incoming else f"REQ-{uuid.uuid4().hex[:20].upper()}"
        g.request_started_monotonic = time.perf_counter()

    @app.after_request
    def _after_request(response):
        started = getattr(g, "request_started_monotonic", time.perf_counter())
        latency_ms = max(0.0, (time.perf_counter() - started) * 1000.0)
        endpoint = request.endpoint or request.path
        request_id = str(getattr(g, "request_id", "unknown"))
        REQUEST_METRICS.record(endpoint, response.status_code, latency_ms)

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-Ms"] = f"{latency_ms:.2f}"
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request.path.startswith("/api/auth") or request.path.startswith("/api/audit"):
            response.headers.setdefault("Cache-Control", "no-store")

        user = _request_user()
        LOGGER.info(
            "request_complete",
            extra={
                "event_type": "request_complete",
                "request_id": request_id,
                "method": request.method,
                "path": request.path,
                "endpoint": endpoint,
                "status_code": response.status_code,
                "latency_ms": round(latency_ms, 2),
                "remote_addr": request.headers.get("X-Forwarded-For", request.remote_addr),
                "user_id": user.get("user_id"),
                "role": user.get("role"),
            },
        )
        return response

    @app.errorhandler(Exception)
    def _unhandled_error(error: Exception):
        if isinstance(error, HTTPException):
            return error
        request_id = str(getattr(g, "request_id", "unknown"))
        REQUEST_METRICS.record_error(request_id, request.path, error)
        LOGGER.exception(
            "unhandled_api_error",
            extra={
                "event_type": "unhandled_api_error",
                "request_id": request_id,
                "method": request.method,
                "path": request.path,
                "endpoint": request.endpoint,
                "status_code": 500,
                "error_type": type(error).__name__,
            },
        )
        if request.path.startswith("/api/"):
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "An unexpected server error occurred.",
                        "request_id": request_id,
                    }
                ),
                500,
            )
        raise error


def metrics_snapshot() -> dict[str, Any]:
    return REQUEST_METRICS.snapshot()


def reset_metrics_for_tests() -> None:
    REQUEST_METRICS.reset()
