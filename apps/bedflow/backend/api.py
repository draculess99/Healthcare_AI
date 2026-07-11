from flask import Flask, Response, g, jsonify, request
import pandas as pd
import json
import os
import threading
import csv
import io
from dotenv import load_dotenv

load_dotenv()

from .models import bedflow_models, DATA_PATH, METRICS_PATH, METRICS_HISTORY_PATH, MODEL_CARD_PATH
from .data_sources import get_data_sources_summary, prepare_diabetes_readmission_data
from .committee import (
    run_committee,
    prepare_committee_context,
    run_safety_agent,
    run_ops_agent,
    run_director_agent
)
from .memory import get_memory_state, append_memory_history, find_similar_bedflow_events
from .audit import log_human_decision, get_audit_log
from .auth import (
    auth_status,
    authenticate,
    can_save_decision,
    can_update_task,
    get_access_log,
    has_permission,
    issue_token,
    list_public_demo_users,
    record_access_event,
    require_auth,
    require_permission,
    sanitize_user,
)
from .command_center import build_hospital_capacity_snapshot, build_discharge_queue
from .discharge_checklist import build_discharge_checklist
from .fhir_adapter import build_fhir_bundle, summarize_bundle
from .tasks import (
    list_tasks,
    sync_tasks_from_checklist,
    update_task_status,
    get_overdue_tasks,
    summarize_tasks,
    list_task_events,
)
from .observability import APP_VERSION, UPGRADE_STAGE, configure_observability, metrics_snapshot
from .readiness import build_readiness_report
from .storage import runtime_storage_status
from .simulator import (
    list_simulation_runs,
    run_capacity_simulation,
    save_simulation_run,
    simulation_capability,
    simulation_runs_csv,
)

app = Flask(__name__)
configure_observability(app)

_QUEUE_SCORE_CACHE = {"key": None, "predictions": None}
_QUEUE_SCORE_LOCK = threading.Lock()


def _clear_queue_score_cache() -> None:
    with _QUEUE_SCORE_LOCK:
        _QUEUE_SCORE_CACHE["key"] = None
        _QUEUE_SCORE_CACHE["predictions"] = None


def _get_scored_demo_patients(df: pd.DataFrame) -> pd.DataFrame:
    """Batch-score the demo table once and reuse it across command-center calls."""
    dataset_mtime = os.stat(DATA_PATH).st_mtime_ns if os.path.exists(DATA_PATH) else 0
    cache_key = (dataset_mtime, bedflow_models.model_version, len(df))
    with _QUEUE_SCORE_LOCK:
        cached = _QUEUE_SCORE_CACHE.get("predictions")
        if _QUEUE_SCORE_CACHE.get("key") == cache_key and isinstance(cached, pd.DataFrame):
            return cached.copy()

    predictions = bedflow_models.predict_dataframe(df)
    with _QUEUE_SCORE_LOCK:
        _QUEUE_SCORE_CACHE["key"] = cache_key
        _QUEUE_SCORE_CACHE["predictions"] = predictions.copy()
    return predictions


@app.route("/api/health", methods=["GET"])
def health():
    """Lightweight liveness endpoint for container and platform probes."""
    return jsonify({
        "status": "ok",
        "app": "BedFlow AI",
        "app_version": APP_VERSION,
        "model_loaded": bedflow_models.is_trained,
        "model_version": bedflow_models.model_version,
        "model_source": "saved artifact" if bedflow_models.loaded_from_artifact else "in-memory model",
        "dataset_ready": os.path.exists(DATA_PATH),
        "upgrade_stage": UPGRADE_STAGE,
        "simulation_ready": True,
        "observability_ready": True,
        "authentication": auth_status(),
        "storage": runtime_storage_status(),
    })


@app.route("/api/ready", methods=["GET"])
def readiness():
    """Deep readiness check for deployment routing and operator diagnostics."""
    report = build_readiness_report()
    return jsonify(report), (200 if report.get("ready") else 503)


@app.route("/api/system/version", methods=["GET"])
def system_version():
    return jsonify({
        "status": "success",
        "app": "BedFlow AI",
        "app_version": APP_VERSION,
        "upgrade_stage": UPGRADE_STAGE,
        "completed_stages": [1, 2, 3, 4, 5, 6, 7, 8, 9, "10A"],
        "persistence": runtime_storage_status(),
        "capabilities": [
            "model-scored discharge queue",
            "role-aware workflow",
            "capacity what-if simulator",
            "FHIR R4-shaped export",
            "persistent JSON runtime directory",
            "health, readiness, metrics, and CI",
        ],
    })


@app.route("/api/metrics", methods=["GET"])
@require_permission("access.read")
def operational_metrics():
    """Administrator-only in-process request metrics for the demo API."""
    return jsonify(metrics_snapshot())

@app.route("/api/auth/demo_users", methods=["GET"])
def auth_demo_users():
    """List non-sensitive local demo identities for the Stage 8 login screen."""
    return jsonify({
        "status": "success",
        "users": list_public_demo_users(),
        "mode": "local-demo-rbac",
        "default_password_hint": "BEDFLOW_DEMO_PASSWORD or BedFlowDemo!",
        "production_ready": False,
    })


@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    data = request.json or {}
    user = authenticate(data.get("username", ""), data.get("password", ""))
    if not user:
        return jsonify({"status": "error", "message": "Invalid username or password"}), 401
    public_user = sanitize_user(user)
    return jsonify({
        "status": "success",
        "token": issue_token(user),
        "user": public_user,
        "expires_in_seconds": auth_status().get("token_max_age_seconds"),
    })


@app.route("/api/auth/me", methods=["GET"])
@require_auth
def auth_me():
    return jsonify({"status": "success", "user": g.bedflow_user})


@app.route("/api/auth/logout", methods=["POST"])
@require_auth
def auth_logout():
    record_access_event("logout", user=g.bedflow_user, outcome="success")
    return jsonify({"status": "success", "message": "Local demo token discarded by client"})


@app.route("/api/auth/role_matrix", methods=["GET"])
def auth_role_matrix():
    users = list_public_demo_users()
    return jsonify({
        "status": "success",
        "roles": [
            {
                "role": user.get("role"),
                "permissions": user.get("permissions", []),
                "allowed_decisions": user.get("allowed_decisions", []),
            }
            for user in users
        ],
    })


@app.route("/api/train_models", methods=["POST"])
@require_permission("model.train")
def train():
    """Train all models and publish versioned model artifacts for Stage 5 governance."""
    try:
        metrics = bedflow_models.train_models(persist_artifacts=True)
        _clear_queue_score_cache()
        return jsonify({
            "status": "success",
            "metrics": metrics,
            "governance": bedflow_models.get_model_governance_summary(),
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/model_governance", methods=["GET"])
def model_governance():
    """Return model lifecycle, artifact, registry, and metrics-history status."""
    try:
        return jsonify(bedflow_models.get_model_governance_summary())
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/load_latest_model", methods=["POST"])
@require_permission("model.manage")
def load_latest_model():
    """Load the latest saved model artifacts into the running backend process."""
    try:
        result = bedflow_models.load_latest_models(silent=False)
        _clear_queue_score_cache()
        status_code = 200 if result.get("status") == "success" else 404
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/model_card", methods=["GET"])
def model_card():
    """Return the generated model card markdown when available."""
    if os.path.exists(MODEL_CARD_PATH):
        with open(MODEL_CARD_PATH, "r", encoding="utf-8") as f:
            return jsonify({"status": "success", "path": MODEL_CARD_PATH, "markdown": f.read()})
    return jsonify({"status": "error", "message": "No model card found. Train models first."}), 404


@app.route("/api/model_metrics_history", methods=["GET"])
def metrics_history():
    if os.path.exists(METRICS_HISTORY_PATH):
        with open(METRICS_HISTORY_PATH, "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    return jsonify([])


@app.route("/api/data_sources", methods=["GET"])
def data_sources():
    """Return Stage 6 training-data provenance and readiness."""
    try:
        ensure = request.args.get("ensure", "false").lower() == "true"
        return jsonify(get_data_sources_summary(ensure_readmission=ensure))
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/prepare_readmission_data", methods=["POST"])
@require_permission("model.manage")
def prepare_readmission_data():
    """Prepare the public diabetes readmission training data layer."""
    try:
        force = (request.json or {}).get("force", False)
        summary = prepare_diabetes_readmission_data(force=bool(force))
        return jsonify({
            "status": "success",
            "summary": summary,
            "data_sources": get_data_sources_summary(ensure_readmission=False),
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/model_metrics", methods=["GET"])
def metrics():
    if os.path.exists(METRICS_PATH):
        with open(METRICS_PATH, "r") as f:
            return jsonify(json.load(f))
    return jsonify({"status": "error", "message": "No metrics found"}), 404

@app.route("/api/demo_patients", methods=["GET"])
def demo_patients():
    if not os.path.exists(DATA_PATH):
        return jsonify([])
    df = pd.read_csv(DATA_PATH, keep_default_na=False)
    return jsonify(df.to_dict(orient="records"))


@app.route("/api/hospital_capacity", methods=["GET"])
def hospital_capacity():
    """Return a simulated capacity snapshot enriched by cached XGBoost scores."""
    if not os.path.exists(DATA_PATH):
        return jsonify({"status": "error", "message": "No patient dataset found"}), 404
    df = pd.read_csv(DATA_PATH, keep_default_na=False)
    try:
        predictions = _get_scored_demo_patients(df)
    except Exception:
        predictions = None
    return jsonify(build_hospital_capacity_snapshot(df, model_predictions=predictions))


@app.route("/api/discharge_queue", methods=["GET"])
def discharge_queue():
    """Return the model-scored prioritized patient discharge-review queue."""
    if not os.path.exists(DATA_PATH):
        return jsonify([])
    df = pd.read_csv(DATA_PATH, keep_default_na=False)
    limit_arg = request.args.get("limit")
    limit = None
    if limit_arg:
        try:
            limit = max(1, int(limit_arg))
        except ValueError:
            limit = None
    try:
        predictions = _get_scored_demo_patients(df)
    except Exception:
        predictions = None
    return jsonify(build_discharge_queue(df, model_predictions=predictions, limit=limit))


@app.route("/api/simulations/capability", methods=["GET"])
def simulations_capability():
    """Describe Stage 9 scenario levers, protected fields, and limitations."""
    return jsonify(simulation_capability())


@app.route("/api/simulations/run", methods=["POST"])
@require_permission("simulation.run")
def simulations_run():
    """Run a model-backed operational counterfactual without retraining."""
    if not os.path.exists(DATA_PATH):
        return jsonify({"status": "error", "message": "No patient dataset found"}), 404
    data = request.json or {}
    scenario = data.get("scenario", data)
    save_requested = bool(data.get("save", False))
    if save_requested and not has_permission(g.bedflow_user, "simulation.save"):
        return jsonify({"status": "error", "message": "This role cannot save simulation runs"}), 403

    try:
        df = pd.read_csv(DATA_PATH, keep_default_na=False)
        current_predictions = _get_scored_demo_patients(df)
        current_capacity = build_hospital_capacity_snapshot(
            df, model_predictions=current_predictions
        )
        result = run_capacity_simulation(
            patient_df=df,
            current_predictions=current_predictions,
            scoring_fn=bedflow_models.predict_dataframe,
            scenario_payload=scenario,
            current_capacity=current_capacity,
            actor=g.bedflow_user,
        )
        if save_requested:
            result = save_simulation_run(result)
        record_access_event(
            "capacity_simulation",
            user=g.bedflow_user,
            outcome="success",
            detail=(
                f"Ran scenario {result.get('simulation_id')} "
                f"(saved={bool(result.get('saved'))})"
            ),
        )
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


@app.route("/api/simulations", methods=["GET"])
@require_permission("simulation.read")
def simulations_history():
    try:
        limit = int(request.args.get("limit", 100))
    except (TypeError, ValueError):
        limit = 100
    return jsonify(list_simulation_runs(
        limit=limit,
        actor_role=request.args.get("actor_role"),
    ))


@app.route("/api/simulations/export.csv", methods=["GET"])
@require_permission("simulation.export")
def simulations_export_csv():
    runs = list_simulation_runs(limit=1000)
    record_access_event(
        "simulation_export",
        user=g.bedflow_user,
        outcome="success",
        detail=f"Exported {len(runs)} saved simulation runs",
    )
    return Response(
        simulation_runs_csv(runs),
        mimetype="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=bedflow_simulation_runs.csv"
        },
    )


@app.route("/api/discharge_checklist", methods=["POST"])
def discharge_checklist():
    """Return a hospital-style discharge readiness checklist for one patient."""
    data = request.json or {}
    patient_data = data.get("patient_data", data)
    model_outputs = data.get("model_outputs", {})
    try:
        return jsonify(build_discharge_checklist(patient_data, model_outputs))
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/explain_patient", methods=["POST"])
def explain_patient():
    """Return patient-level model explanations and risk reasons."""
    data = request.json or {}
    patient_data = data.get("patient_data", data)
    model_outputs = data.get("model_outputs")
    try:
        top_n = int(data.get("top_n", 5))
    except (TypeError, ValueError):
        top_n = 5
    try:
        return jsonify(bedflow_models.explain_patient(patient_data, model_outputs, top_n=top_n))
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/model_feature_importance", methods=["GET"])
def model_feature_importance():
    """Return global model feature-importance summaries for the active in-memory models."""
    try:
        top_n = int(request.args.get("top_n", 12))
    except (TypeError, ValueError):
        top_n = 12
    try:
        return jsonify(bedflow_models.get_global_feature_importance(top_n=top_n))
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500





@app.route("/api/fhir/bundle", methods=["POST"])
@require_permission("fhir.export")
def fhir_bundle():
    """Build a de-identified FHIR R4-shaped collection bundle for one patient case."""
    data = request.json or {}
    patient_data = data.get("patient_data", {})
    if not patient_data:
        return jsonify({"status": "error", "message": "patient_data is required"}), 400
    checklist = data.get("discharge_checklist") or build_discharge_checklist(
        patient_data, data.get("model_outputs", {})
    )
    task_snapshot = data.get("tasks")
    if task_snapshot is None:
        task_snapshot = list_tasks(patient_id=str(patient_data.get("patient_id", "")))
    bundle = build_fhir_bundle(
        patient_data,
        model_outputs=data.get("model_outputs", {}),
        checklist=checklist,
        tasks=task_snapshot,
    )
    return jsonify({"status": "success", "summary": summarize_bundle(bundle), "bundle": bundle})


@app.route("/api/fhir/capability", methods=["GET"])
def fhir_capability():
    """Describe the demonstration adapter's supported FHIR-shaped resources."""
    return jsonify({
        "status": "success",
        "fhir_version": "4.0.1-shaped demo output",
        "mode": "export-only adapter; not a certified FHIR server",
        "resources": ["Patient", "Encounter", "Observation", "Task", "CarePlan", "Location", "Bundle"],
        "privacy": "Synthetic/proxy de-identified demo data only; no PHI.",
    })

@app.route("/api/tasks", methods=["GET"])
def tasks():
    """Return task workflow records, optionally filtered by patient, owner, or status."""
    patient_id = request.args.get("patient_id")
    owner = request.args.get("owner")
    status = request.args.get("status")
    include_completed = request.args.get("include_completed", "true").lower() != "false"
    return jsonify(list_tasks(
        patient_id=patient_id,
        owner=owner,
        status=status,
        include_completed=include_completed,
    ))


@app.route("/api/tasks/summary", methods=["GET"])
def task_summary():
    """Return task counts for the hospital workflow dashboard."""
    return jsonify(summarize_tasks())


@app.route("/api/tasks/overdue", methods=["GET"])
def overdue_tasks():
    """Return active tasks that have passed their SLA timer."""
    return jsonify(get_overdue_tasks())


@app.route("/api/tasks/sync", methods=["POST"])
@require_permission("task.sync")
def sync_tasks():
    """Create or refresh workflow tasks from one patient's checklist blockers."""
    data = request.json or {}
    patient_data = data.get("patient_data", {})
    checklist = data.get("discharge_checklist") or build_discharge_checklist(
        patient_data,
        data.get("model_outputs", {}),
    )
    try:
        return jsonify(sync_tasks_from_checklist(patient_data, checklist))
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/tasks/sync_all", methods=["POST"])
@require_permission("task.sync")
def sync_all_tasks():
    """Create or refresh workflow tasks for the top patients in the demo dataset."""
    if not os.path.exists(DATA_PATH):
        return jsonify({"status": "error", "message": "No patient dataset found"}), 404
    data = request.json or {}
    try:
        limit = int(data.get("limit", 75))
    except (TypeError, ValueError):
        limit = 75
    limit = max(1, min(limit, 300))

    df = pd.read_csv(DATA_PATH, keep_default_na=False)
    try:
        predictions = _get_scored_demo_patients(df)
    except Exception:
        predictions = None
    queue = build_discharge_queue(df, model_predictions=predictions, limit=limit)
    records_by_id = {str(row.get("patient_id")): row for row in df.to_dict(orient="records")}
    created = 0
    refreshed = 0
    processed = 0
    for queue_item in queue:
        record = records_by_id.get(str(queue_item.get("patient_id")))
        if not record:
            continue
        record["unit"] = queue_item.get("unit", "Unknown")
        checklist = build_discharge_checklist(record)
        result = sync_tasks_from_checklist(record, checklist)
        created += result.get("created_count", 0)
        refreshed += result.get("refreshed_count", 0)
        processed += 1

    return jsonify({
        "status": "success",
        "patients_processed": processed,
        "created_count": created,
        "refreshed_count": refreshed,
        "summary": summarize_tasks(),
    })


@app.route("/api/tasks/update_status", methods=["POST"])
@require_auth
def update_task():
    """Update one task with backend-enforced role ownership."""
    data = request.json or {}
    task_id = data.get("task_id")
    existing = next((task for task in list_tasks() if task.get("task_id") == task_id), None)
    if not existing:
        return jsonify({"status": "error", "message": f"Task not found: {task_id}"}), 404
    if not can_update_task(g.bedflow_user, existing):
        record_access_event(
            "task_update",
            user=g.bedflow_user,
            outcome="denied",
            detail=f"Task is owned by {existing.get('owner_role')}",
            patient_id=existing.get("patient_id"),
            task_id=task_id,
        )
        return jsonify({
            "status": "error",
            "message": (
                f"Role '{g.bedflow_user.get('role')}' cannot update a task owned by "
                f"'{existing.get('owner_role')}'."
            ),
        }), 403
    try:
        task = update_task_status(
            task_id=task_id,
            status=data.get("status"),
            note=data.get("note", ""),
            updated_by=g.bedflow_user.get("display_name", "Authenticated user"),
            updated_by_role=g.bedflow_user.get("role"),
            updated_by_user_id=g.bedflow_user.get("user_id"),
        )
        record_access_event(
            "task_update",
            user=g.bedflow_user,
            outcome="success",
            detail=f"Status changed to {task.get('status')}",
            patient_id=task.get("patient_id"),
            task_id=task_id,
        )
        return jsonify({"status": "success", "task": task})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400



@app.route("/api/tasks/<patient_id>", methods=["GET"])
def patient_tasks(patient_id):
    """Return all workflow tasks for a selected patient."""
    return jsonify(list_tasks(patient_id=patient_id))

@app.route("/api/tasks/events", methods=["GET"])
@require_permission("audit.read")
def task_events():
    try:
        limit = int(request.args.get("limit", 500))
    except (TypeError, ValueError):
        limit = 500
    return jsonify(list_task_events(
        patient_id=request.args.get("patient_id"),
        task_id=request.args.get("task_id"),
        actor_role=request.args.get("actor_role"),
        limit=limit,
    ))


@app.route("/api/predict_patient", methods=["POST"])
def predict():
    data = request.json
    try:
        preds = bedflow_models.predict_patient(data)
        return jsonify(preds)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/run_committee", methods=["POST"])
def committee():
    data = request.json
    patient_data = data.get("patient_data", {})
    model_outputs = data.get("model_outputs", {})
    decision_system = data.get("decision_system", "Internal Expert System")
    model_name = data.get("model_name", None)
    try:
        result = run_committee(patient_data, model_outputs, decision_system, model_name)
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/agent/prepare", methods=["POST"])
def prepare_agent_context():
    data = request.json
    try:
        ctx = prepare_committee_context(data.get("patient_data", {}), data.get("model_outputs", {}))
        return jsonify(ctx)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/agent/safety", methods=["POST"])
def agent_safety():
    data = request.json
    res, tok, err = run_safety_agent(data.get("context"), data.get("decision_system"), data.get("model_name"))
    return jsonify({"result": res, "token_usage": tok, "error": err})

@app.route("/api/agent/ops", methods=["POST"])
def agent_ops():
    data = request.json
    res, tok, err = run_ops_agent(data.get("context"), data.get("decision_system"), data.get("model_name"))
    return jsonify({"result": res, "token_usage": tok, "error": err})

@app.route("/api/agent/director", methods=["POST"])
def agent_director():
    data = request.json
    res_json, tok, err = run_director_agent(
        data.get("context"), 
        data.get("safety_arg"), 
        data.get("ops_arg"), 
        data.get("decision_system"), 
        data.get("model_name")
    )
    return jsonify({"result": res_json, "token_usage": tok, "error": err})

@app.route("/api/memory_state", methods=["GET"])
def memory_state():
    return jsonify(get_memory_state())

@app.route("/api/save_human_decision", methods=["POST"])
@require_permission("decision.save")
def save_decision():
    data = request.json or {}
    decision = str(data.get("human_decision", "")).strip()
    note = str(data.get("human_note", "")).strip()
    reviewer_name = str(g.bedflow_user.get("display_name", "")).strip()
    reviewer_role = str(g.bedflow_user.get("role", "")).strip()
    if not data.get("patient_id") or not decision:
        return jsonify({"status": "error", "message": "patient_id and human_decision are required"}), 400
    if not can_save_decision(g.bedflow_user, decision):
        record_access_event(
            "human_decision",
            user=g.bedflow_user,
            outcome="denied",
            detail=f"Decision '{decision}' is not permitted for this role",
            patient_id=data.get("patient_id"),
        )
        return jsonify({
            "status": "error",
            "message": f"Role '{reviewer_role}' is not permitted to record action '{decision}'.",
        }), 403
    if decision in {"Override", "Escalate to Case Manager", "Hold"} and not note:
        return jsonify({"status": "error", "message": "A reason is required for override, escalation, or hold decisions"}), 400
    try:
        record = log_human_decision(
            patient_id=data.get("patient_id"),
            model_outputs=data.get("model_outputs") or {},
            research_outputs=data.get("research_outputs") or {},
            committee_rec=data.get("committee_recommendation"),
            human_decision=decision,
            human_note=note,
            memory_insight=data.get("memory_insight"),
            discharge_checklist=data.get("discharge_checklist"),
            task_snapshot=data.get("task_snapshot"),
            model_explanations=data.get("model_explanations"),
            reviewer_name=reviewer_name,
            reviewer_role=reviewer_role,
            reviewer_user_id=g.bedflow_user.get("user_id"),
            authentication_source="local-demo-rbac",
            model_version=(data.get("model_outputs") or {}).get("model_version") or bedflow_models.model_version,
        )
        
        # Append to memory history
        history_record = {
            "patient_id": data.get("patient_id"),
            "scenario_signature": {
                "primary_bottleneck": data.get("patient_data", {}).get("primary_discharge_bottleneck", "None"),
                "readmission_risk_level": data.get("model_outputs", {}).get("readmission_risk_level", "Low"),
                "delay_risk_level": data.get("model_outputs", {}).get("delay_risk_level", "Low"),
                "discharge_destination": data.get("patient_data", {}).get("discharge_destination", "Home"),
                "home_support_level": data.get("patient_data", {}).get("home_support_level", "Good"),
                "bed_occupancy_percent": data.get("patient_data", {}).get("current_bed_occupancy_percent", 80),
                "ed_boarding_count": data.get("patient_data", {}).get("ed_boarding_count", 0)
            },
            "model_outputs": data.get("model_outputs"),
            "research_outputs": data.get("research_outputs"),
            "committee_recommendation": data.get("committee_recommendation"),
            "human_decision": data.get("human_decision"),
            "outcome_proxy": "Unknown",
            "memory_reasoning": "Appended from human decision."
        }
        append_memory_history(history_record)
        record_access_event(
            "human_decision",
            user=g.bedflow_user,
            outcome="success",
            detail=f"Recorded {decision}",
            patient_id=data.get("patient_id"),
        )
        
        return jsonify({"status": "success", "record": record})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/audit_log", methods=["GET"])
@require_permission("audit.read")
def audit():
    return jsonify(get_audit_log())


@app.route("/api/audit/export.csv", methods=["GET"])
@require_permission("audit.export")
def audit_export_csv():
    records = get_audit_log()
    output = io.StringIO()
    fieldnames = [
        "audit_id",
        "timestamp_utc",
        "patient_id",
        "reviewer_user_id",
        "reviewer_name",
        "reviewer_role",
        "human_decision",
        "human_note",
        "committee_recommendation",
        "risk_level",
        "readmission_risk_level",
        "model_version",
        "authentication_source",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for record in records:
        writer.writerow(record)
    record_access_event("audit_export", user=g.bedflow_user, outcome="success", detail=f"Exported {len(records)} records")
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=bedflow_audit_export.csv"},
    )


@app.route("/api/access_log", methods=["GET"])
@require_permission("access.read")
def access_log():
    return jsonify(get_access_log())


if __name__ == "__main__":
    host = os.getenv("BEDFLOW_API_HOST", "127.0.0.1")
    port = int(os.getenv("BEDFLOW_API_PORT", "5005"))
    app.run(host=host, port=port)
