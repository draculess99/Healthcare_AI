import logging
import os
import json
from datetime import datetime

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
LOG_FILE = os.path.join(LOG_DIR, 'transactions.log')
AUDIT_FILE = os.path.join(LOG_DIR, 'audit_trail.jsonl')


def _utc_timestamp():
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _append_jsonl(path, payload):
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(payload, default=str) + '\n')


def _read_jsonl(path, limit=None):
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                # Keep the API resilient if an old/bad line ever appears.
                continue
    if limit:
        rows = rows[-int(limit):]
    return rows


def log_transaction(action, details):
    """Appends a transaction to the log file."""
    log_entry = {
        "timestamp": _utc_timestamp(),
        "action": action,
        "details": details
    }
    _append_jsonl(LOG_FILE, log_entry)
    return log_entry


def log_audit_event(event_type, patient_id=None, action="", details=None, source="frontend", session_id="demo_session"):
    """Persist a clinician/workflow audit event to a JSONL audit trail.

    This is separate from model transaction logging. Transactions explain what the
    model/agent pipeline did; audit events explain what the clinical workflow UI
    did after the recommendation: queue entry, nurse confirmation/override,
    escalation, rooming, reassessment, discharge/removal, etc.
    """
    audit_entry = {
        "timestamp": _utc_timestamp(),
        "session_id": session_id,
        "patient_id": patient_id,
        "event_type": event_type,
        "action": action,
        "source": source,
        "details": details or {},
    }
    _append_jsonl(AUDIT_FILE, audit_entry)
    return audit_entry


def read_audit_trail(limit=250):
    """Read the persistent nurse/workflow audit trail."""
    return _read_jsonl(AUDIT_FILE, limit=limit)
