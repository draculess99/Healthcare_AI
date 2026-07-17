from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from flask import Flask, jsonify, request

from backend.agents.committee import PIPELINE_STAGES, run_pipeline
from backend.memory import JSONMemoryStore
from backend.model import DenialRiskModel
from backend.rag import PolicyRAG


def create_app() -> Flask:
    app = Flask(__name__)
    store = JSONMemoryStore()

    @app.after_request
    def add_cors_headers(response: Any) -> Any:
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return response

    @app.get("/health")
    def health() -> Any:
        return jsonify({
            "status": "ok",
            "service": "AuthGuard AI API",
            "pipeline_stages": len(PIPELINE_STAGES),
            "time": datetime.now(timezone.utc).isoformat(),
        })

    @app.post("/api/process")
    def process_case() -> Any:
        payload = request.get_json(silent=True) or {}
        case = payload.get("case") or payload
        provider = payload.get("provider", "Local Expert System")
        provider_model = payload.get("provider_model") or payload.get("model")
        try:
            return jsonify(
                run_pipeline(
                    case,
                    provider=provider,
                    provider_model=provider_model,
                    memory_store=store,
                )
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"error": f"Pipeline failed: {exc}"}), 500

    @app.post("/api/review")
    def save_review() -> Any:
        payload = request.get_json(silent=True) or {}
        required = ["run_id", "case_id", "reviewer", "action"]
        missing = [field for field in required if not str(payload.get(field, "")).strip()]
        if missing:
            return jsonify({"error": "Missing fields: " + ", ".join(missing)}), 400
        record = {
            **payload,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        }
        store.append_audit(record)
        return jsonify({"status": "saved", "record": record}), 201

    @app.get("/api/cases")
    def list_cases() -> Any:
        return jsonify(store.list_cases(limit=int(request.args.get("limit", 50))))

    @app.get("/api/memory")
    def list_memory() -> Any:
        return jsonify(store.list_memory(limit=int(request.args.get("limit", 50))))

    @app.get("/api/audit")
    def list_audit() -> Any:
        return jsonify(store.list_audit(limit=int(request.args.get("limit", 50))))

    @app.get("/api/model/metrics")
    def model_metrics() -> Any:
        return jsonify(DenialRiskModel().metrics)

    @app.get("/api/knowledge")
    def knowledge() -> Any:
        rag = PolicyRAG()
        return jsonify(rag.documents)

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("AUTHGUARD_API_PORT", "5008"))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
