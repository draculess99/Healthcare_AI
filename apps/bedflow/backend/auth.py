"""Local demonstration authentication and role-based access control for BedFlow AI.

Stage 8 adds authenticated local demo identities, signed bearer tokens, backend
permission enforcement, and access-event logging. This module is suitable for a
portfolio demonstration only. Production deployments should replace it with an
enterprise identity provider, HTTPS, secret rotation, and managed identity and database-backed users.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import uuid
from functools import wraps
from typing import Any, Callable

from flask import g, has_request_context, jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

from .storage import runtime_json_path

USERS_PATH = runtime_json_path("demo_users.json", [])
ACCESS_LOG_PATH = runtime_json_path("access_log.json", [])
TOKEN_SALT = "bedflow-stage8-auth"
TOKEN_MAX_AGE_SECONDS = int(os.getenv("BEDFLOW_TOKEN_MAX_AGE_SECONDS", "28800"))
DEFAULT_DEMO_PASSWORD = os.getenv("BEDFLOW_DEMO_PASSWORD", "BedFlowDemo!")
DEFAULT_AUTH_SECRET = "bedflow-local-demo-secret-change-me"
AUTH_SECRET = os.getenv("BEDFLOW_AUTH_SECRET", DEFAULT_AUTH_SECRET)

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "Administrator": {
        "model.train",
        "model.manage",
        "task.sync",
        "task.update_any",
        "decision.save",
        "decision.approve",
        "decision.override",
        "decision.escalate",
        "decision.hold",
        "audit.read",
        "audit.export",
        "access.read",
        "fhir.export",
        "simulation.run",
        "simulation.save",
        "simulation.read",
        "simulation.export",
    },
    "Bed Manager": {
        "task.sync",
        "task.update_any",
        "decision.save",
        "decision.approve",
        "decision.override",
        "decision.escalate",
        "decision.hold",
        "audit.read",
        "fhir.export",
        "simulation.run",
        "simulation.save",
        "simulation.read",
        "simulation.export",
    },
    "Physician": {
        "task.update_own",
        "decision.save",
        "decision.approve",
        "decision.override",
        "decision.escalate",
        "decision.hold",
        "audit.read",
        "fhir.export",
        "simulation.read",
    },
    "Nurse": {
        "task.update_own",
        "decision.save",
        "decision.escalate",
        "decision.hold",
        "audit.read",
        "fhir.export",
        "simulation.read",
    },
    "Pharmacist": {"task.update_own", "audit.read", "fhir.export", "simulation.read"},
    "Case Manager": {
        "task.update_own",
        "decision.save",
        "decision.escalate",
        "decision.hold",
        "audit.read",
        "fhir.export",
        "simulation.read",
    },
    "Utilization Manager": {
        "task.update_own",
        "decision.save",
        "decision.escalate",
        "decision.hold",
        "audit.read",
        "fhir.export",
        "simulation.read",
    },
    "Social Worker": {"task.update_own", "audit.read", "fhir.export", "simulation.read"},
    "Transport Coordinator": {"task.update_own", "audit.read", "fhir.export", "simulation.read"},
}

DECISION_PERMISSION = {
    "Approve": "decision.approve",
    "Override": "decision.override",
    "Escalate to Case Manager": "decision.escalate",
    "Hold": "decision.hold",
}

OWNER_ROLE_ALIASES = {
    "Pharmacy": "Pharmacist",
    "Pharmacist": "Pharmacist",
    "Utilization Management": "Utilization Manager",
    "Utilization Manager": "Utilization Manager",
    "Family / Case Manager": "Case Manager",
    "Case Manager": "Case Manager",
    "Transport": "Transport Coordinator",
    "Transport Coordinator": "Transport Coordinator",
    "Physician": "Physician",
    "Nurse": "Nurse",
    "Social Worker": "Social Worker",
    "Bed Manager": "Bed Manager",
}

DEFAULT_USERS = [
    ("admin", "Demo Administrator", "Administrator", "Platform Administration"),
    ("bedmanager", "Jordan Lee", "Bed Manager", "Patient Flow"),
    ("physician", "Dr. Maya Patel", "Physician", "Hospital Medicine"),
    ("nurse", "Alex Morgan, RN", "Nurse", "Care Coordination"),
    ("pharmacist", "Taylor Chen, PharmD", "Pharmacist", "Pharmacy"),
    ("casemanager", "Sam Rivera", "Case Manager", "Case Management"),
    ("utilization", "Chris Bennett", "Utilization Manager", "Utilization Management"),
    ("socialworker", "Jamie Brooks", "Social Worker", "Social Work"),
    ("transport", "Morgan Davis", "Transport Coordinator", "Patient Transport"),
]


def _iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _atomic_write(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    os.replace(temp_path, path)


def _load_json_list(path: str) -> list[dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def init_demo_users() -> list[dict[str, Any]]:
    users = _load_json_list(USERS_PATH)
    if users:
        return users

    users = []
    for username, display_name, role, department in DEFAULT_USERS:
        users.append(
            {
                "user_id": f"USR-{uuid.uuid4().hex[:12].upper()}",
                "username": username,
                "display_name": display_name,
                "role": role,
                "department": department,
                "password_hash": generate_password_hash(DEFAULT_DEMO_PASSWORD),
                "active": True,
                "created_at": _iso_now(),
            }
        )
    _atomic_write(USERS_PATH, users)
    return users


def list_public_demo_users() -> list[dict[str, Any]]:
    return [sanitize_user(user) for user in init_demo_users() if user.get("active", True)]


def sanitize_user(user: dict[str, Any]) -> dict[str, Any]:
    role = str(user.get("role", ""))
    permissions = sorted(ROLE_PERMISSIONS.get(role, set()))
    allowed_decisions = [
        action for action, permission in DECISION_PERMISSION.items() if permission in permissions
    ]
    return {
        "user_id": user.get("user_id"),
        "username": user.get("username"),
        "display_name": user.get("display_name"),
        "role": role,
        "department": user.get("department"),
        "active": bool(user.get("active", True)),
        "permissions": permissions,
        "allowed_decisions": allowed_decisions,
    }


def find_user(username: str) -> dict[str, Any] | None:
    normalized = str(username or "").strip().lower()
    for user in init_demo_users():
        if str(user.get("username", "")).strip().lower() == normalized:
            return user
    return None


def authenticate(username: str, password: str) -> dict[str, Any] | None:
    user = find_user(username)
    if not user or not user.get("active", True):
        record_access_event("login_failed", username=username, outcome="denied", detail="Unknown or inactive user")
        return None
    if not check_password_hash(str(user.get("password_hash", "")), str(password or "")):
        record_access_event("login_failed", user=user, outcome="denied", detail="Invalid password")
        return None
    record_access_event("login", user=user, outcome="success")
    return user


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(AUTH_SECRET, salt=TOKEN_SALT)


def issue_token(user: dict[str, Any]) -> str:
    payload = {
        "sub": user.get("user_id"),
        "username": user.get("username"),
        "issued_at": _iso_now(),
        "nonce": uuid.uuid4().hex,
    }
    return _serializer().dumps(payload)


def verify_token(token: str) -> dict[str, Any] | None:
    try:
        payload = _serializer().loads(token, max_age=TOKEN_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None

    user = find_user(str(payload.get("username", "")))
    if not user or not user.get("active", True):
        return None
    if str(user.get("user_id")) != str(payload.get("sub")):
        return None
    return sanitize_user(user)


def current_user_from_request() -> dict[str, Any] | None:
    header = request.headers.get("Authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    token = header.split(" ", 1)[1].strip()
    return verify_token(token)


def has_permission(user: dict[str, Any] | None, permission: str) -> bool:
    if not user:
        return False
    return permission in set(user.get("permissions", []))


def require_auth(view: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any):
        user = current_user_from_request()
        if not user:
            record_access_event("authorization", outcome="denied", detail=f"Authentication required for {request.path}")
            return jsonify({"status": "error", "message": "Authentication required"}), 401
        g.bedflow_user = user
        return view(*args, **kwargs)

    return wrapped


def require_permission(permission: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(view: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(view)
        def wrapped(*args: Any, **kwargs: Any):
            user = current_user_from_request()
            if not user:
                record_access_event("authorization", outcome="denied", detail=f"Authentication required for {request.path}")
                return jsonify({"status": "error", "message": "Authentication required"}), 401
            g.bedflow_user = user
            if not has_permission(user, permission):
                record_access_event(
                    "authorization",
                    user=user,
                    outcome="denied",
                    detail=f"Missing permission {permission} for {request.path}",
                )
                return jsonify(
                    {
                        "status": "error",
                        "message": f"Role '{user.get('role')}' does not have permission '{permission}'",
                    }
                ), 403
            return view(*args, **kwargs)

        return wrapped

    return decorator


def normalized_owner_role(owner_role: str) -> str:
    return OWNER_ROLE_ALIASES.get(str(owner_role or "").strip(), str(owner_role or "").strip())


def can_update_task(user: dict[str, Any], task: dict[str, Any]) -> bool:
    if has_permission(user, "task.update_any"):
        return True
    if not has_permission(user, "task.update_own"):
        return False
    return normalized_owner_role(str(task.get("owner_role", ""))) == str(user.get("role", ""))


def can_save_decision(user: dict[str, Any], action: str) -> bool:
    permission = DECISION_PERMISSION.get(str(action or "").strip())
    return bool(permission and has_permission(user, "decision.save") and has_permission(user, permission))


def record_access_event(
    event_type: str,
    user: dict[str, Any] | None = None,
    username: str | None = None,
    outcome: str = "success",
    detail: str = "",
    patient_id: str | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    event = {
        "event_id": f"ACCESS-{uuid.uuid4().hex[:16].upper()}",
        "timestamp_utc": _iso_now(),
        "event_type": event_type,
        "outcome": outcome,
        "user_id": (user or {}).get("user_id"),
        "username": (user or {}).get("username") or username,
        "display_name": (user or {}).get("display_name"),
        "role": (user or {}).get("role"),
        "patient_id": patient_id,
        "task_id": task_id,
        "request_path": request.path if has_request_context() else None,
        "detail": detail,
    }
    events = _load_json_list(ACCESS_LOG_PATH)
    events.append(event)
    _atomic_write(ACCESS_LOG_PATH, events)
    return event


def get_access_log() -> list[dict[str, Any]]:
    return _load_json_list(ACCESS_LOG_PATH)


def auth_status() -> dict[str, Any]:
    return {
        "mode": "local-demo-rbac",
        "token_max_age_seconds": TOKEN_MAX_AGE_SECONDS,
        "using_default_secret": AUTH_SECRET == DEFAULT_AUTH_SECRET,
        "demo_user_count": len(init_demo_users()),
        "production_ready": False,
    }
