from __future__ import annotations

import csv
import io
import ipaddress
import json
import os
import socket
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

import numpy as np
import requests

from backend.guardrails import validate_case

MAX_LIVE_BYTES = int(os.getenv("AUTHGUARD_LIVE_DATA_MAX_BYTES", str(5 * 1024 * 1024)))
MAX_LIVE_RECORDS = int(os.getenv("AUTHGUARD_LIVE_DATA_MAX_RECORDS", "5000"))

PAYER_OPTIONS = ["Medicare", "Medicaid", "Commercial A", "Commercial B", "Self Pay"]
SERVICE_OPTIONS = [
    "Advanced Imaging",
    "Specialty Medication",
    "Surgery",
    "DME",
    "Rehabilitation",
    "Post-Acute Placement",
]
DIAGNOSIS_OPTIONS = ["Neurologic", "Rheumatology", "Orthopedic", "Cardiology", "Oncology", "Other"]

REQUIRED_FIELDS = ("case_id", "payer", "service_type", "diagnosis_group")

ALIASES: dict[str, tuple[str, ...]] = {
    "case_id": ("case_id", "id", "authorization_id", "request_id", "auth_id"),
    "payer": ("payer", "payer_name", "insurer", "health_plan"),
    "service_type": ("service_type", "service", "procedure_category", "request_type"),
    "diagnosis_group": ("diagnosis_group", "diagnosis_category", "diagnosis", "condition_group"),
    "age_years": ("age_years", "age", "patient_age"),
    "urgent": ("urgent", "expedited", "is_urgent"),
    "inpatient": ("inpatient", "is_inpatient"),
    "prior_auth_required": ("prior_auth_required", "pa_required", "authorization_required"),
    "member_eligible": ("member_eligible", "eligible", "eligibility_confirmed"),
    "in_network": ("in_network", "network_status", "provider_in_network"),
    "requested_units": ("requested_units", "units", "requested_days"),
    "evidence_count": ("evidence_count", "documents_received", "evidence_items"),
    "required_document_count": ("required_document_count", "documents_required", "required_items"),
    "conservative_therapy_weeks": ("conservative_therapy_weeks", "therapy_weeks"),
    "guideline_min_weeks": ("guideline_min_weeks", "minimum_therapy_weeks", "policy_min_weeks"),
    "failed_conservative_therapy": ("failed_conservative_therapy", "therapy_failed"),
    "specialist_order": ("specialist_order", "has_specialist_order"),
    "estimated_cost": ("estimated_cost", "cost", "estimated_amount"),
    "previous_denials": ("previous_denials", "prior_denials", "denial_count"),
    "clinical_notes": ("clinical_notes", "notes", "deidentified_notes", "summary"),
}

DEFAULTS: dict[str, Any] = {
    "age_years": 50,
    "urgent": False,
    "inpatient": False,
    "prior_auth_required": True,
    "member_eligible": True,
    "in_network": True,
    "requested_units": 1,
    "evidence_count": 0,
    "required_document_count": 0,
    "conservative_therapy_weeks": 0,
    "guideline_min_weeks": 0,
    "failed_conservative_therapy": False,
    "specialist_order": False,
    "estimated_cost": 0,
    "previous_denials": 0,
    "clinical_notes": "De-identified external record.",
}

BOOL_FIELDS = {
    "urgent",
    "inpatient",
    "prior_auth_required",
    "member_eligible",
    "in_network",
    "failed_conservative_therapy",
    "specialist_order",
}
INT_FIELDS = {
    "age_years",
    "requested_units",
    "evidence_count",
    "required_document_count",
    "conservative_therapy_weeks",
    "guideline_min_weeks",
    "previous_denials",
}
FLOAT_FIELDS = {"estimated_cost"}


def _first(record: dict[str, Any], names: Iterable[str]) -> Any:
    lower_map = {str(key).strip().lower(): value for key, value in record.items()}
    for name in names:
        if name.lower() in lower_map and lower_map[name.lower()] not in (None, ""):
            return lower_map[name.lower()]
    return None


def _to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on", "in network", "eligible", "confirmed", "urgent"}:
        return True
    if normalized in {"0", "false", "no", "n", "off", "out of network", "ineligible", "standard"}:
        return False
    return default


def _to_number(value: Any, default: int | float, integer: bool) -> int | float:
    if value is None or value == "":
        return default
    try:
        number = float(str(value).replace(",", "").replace("$", "").strip())
        return int(round(number)) if integer else number
    except (TypeError, ValueError):
        return default


def normalize_case_record(record: dict[str, Any], index: int = 0) -> dict[str, Any]:
    """Map a de-identified CSV/JSON record into the AuthGuard case schema."""
    normalized: dict[str, Any] = {}
    for target, aliases in ALIASES.items():
        value = _first(record, aliases)
        if value is None:
            value = DEFAULTS.get(target)
        if target in BOOL_FIELDS:
            value = _to_bool(value, bool(DEFAULTS.get(target, False)))
        elif target in INT_FIELDS:
            value = _to_number(value, int(DEFAULTS.get(target, 0)), integer=True)
        elif target in FLOAT_FIELDS:
            value = _to_number(value, float(DEFAULTS.get(target, 0.0)), integer=False)
        elif value is not None:
            value = str(value).strip()
        normalized[target] = value

    if not normalized.get("case_id"):
        normalized["case_id"] = f"LIVE-{index + 1:04d}"
    normalized["data_source"] = "live_external"
    return normalized


def validate_case_records(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    valid: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, record in enumerate(records):
        normalized = normalize_case_record(record, index=index)
        record_errors = validate_case(normalized)
        if record_errors:
            errors.append(f"Record {index + 1}: " + "; ".join(record_errors))
        else:
            valid.append(normalized)
    return valid, errors


def _parse_json(content: bytes) -> list[dict[str, Any]]:
    payload = json.loads(content.decode("utf-8-sig"))
    if isinstance(payload, dict):
        for key in ("cases", "records", "data", "items"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
        else:
            payload = [payload]
    if not isinstance(payload, list):
        raise ValueError("JSON live dataset must be an object or a list of objects")
    return [row for row in payload if isinstance(row, dict)]


def _parse_csv(content: bytes) -> list[dict[str, Any]]:
    text = content.decode("utf-8-sig")
    return [dict(row) for row in csv.DictReader(io.StringIO(text))]


def parse_live_content(content: bytes, filename: str = "dataset.json", content_type: str = "") -> list[dict[str, Any]]:
    if len(content) > MAX_LIVE_BYTES:
        raise ValueError(f"Live dataset exceeds the {MAX_LIVE_BYTES:,}-byte safety limit")
    suffix = Path(filename.split("?", 1)[0]).suffix.lower()
    lowered_type = content_type.lower()
    if suffix == ".csv" or "text/csv" in lowered_type:
        raw = _parse_csv(content)
    elif suffix in {".json", ".jsonl"} or "json" in lowered_type:
        if suffix == ".jsonl":
            raw = [json.loads(line) for line in content.decode("utf-8-sig").splitlines() if line.strip()]
        else:
            raw = _parse_json(content)
    else:
        # Try JSON first, then CSV so generic API content-types still work.
        try:
            raw = _parse_json(content)
        except Exception:
            raw = _parse_csv(content)
    if not raw:
        raise ValueError("Live dataset contained no records")
    if len(raw) > MAX_LIVE_RECORDS:
        raise ValueError(f"Live dataset exceeds the {MAX_LIVE_RECORDS:,}-record safety limit")
    valid, errors = validate_case_records(raw)
    if not valid:
        detail = errors[0] if errors else "No valid records"
        raise ValueError(f"Live dataset failed AuthGuard schema validation: {detail}")
    return valid


def _is_private_host(hostname: str) -> bool:
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(hostname, None)}
    except socket.gaierror:
        return False
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return True
        except ValueError:
            continue
    return False


def validate_live_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Live dataset URL must use http or https")
    allow_private = os.getenv("AUTHGUARD_ALLOW_PRIVATE_LIVE_URL", "false").strip().lower() == "true"
    if not allow_private and parsed.hostname and _is_private_host(parsed.hostname):
        raise ValueError("Private or loopback live-data URLs are blocked by default")
    return url.strip()


def load_live_cases(
    *,
    url: str | None = None,
    file_bytes: bytes | None = None,
    filename: str | None = None,
    bearer_token: str | None = None,
    timeout: float | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load de-identified case records from a CSV/JSON upload or external URL."""
    if file_bytes is not None:
        records = parse_live_content(file_bytes, filename or "uploaded.json")
        return records, {
            "mode": "live_external",
            "transport": "upload",
            "source": filename or "uploaded file",
            "records": len(records),
        }

    configured_url = (url or os.getenv("AUTHGUARD_LIVE_DATA_URL", "")).strip()
    if not configured_url:
        raise ValueError("No live dataset URL is configured and no file was uploaded")
    safe_url = validate_live_url(configured_url)
    headers = {"Accept": "application/json, text/csv;q=0.9, */*;q=0.1"}
    token = (bearer_token or os.getenv("AUTHGUARD_LIVE_DATA_BEARER_TOKEN", "")).strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = requests.get(
        safe_url,
        headers=headers,
        timeout=timeout or float(os.getenv("AUTHGUARD_LIVE_DATA_TIMEOUT", "20")),
    )
    response.raise_for_status()
    content = response.content
    records = parse_live_content(
        content,
        filename=Path(urlparse(safe_url).path).name or "live-dataset.json",
        content_type=response.headers.get("Content-Type", ""),
    )
    return records, {
        "mode": "live_external",
        "transport": "url",
        "source": safe_url,
        "records": len(records),
    }


def generate_synthetic_cases(count: int = 24, seed: int = 42) -> list[dict[str, Any]]:
    """Generate reproducible demonstration cases; no patient or payer records are used."""
    if count < 1 or count > MAX_LIVE_RECORDS:
        raise ValueError("Synthetic case count must be between 1 and the configured record limit")
    rng = np.random.default_rng(seed)
    cases: list[dict[str, Any]] = []
    for index in range(count):
        required_docs = int(rng.integers(3, 8))
        evidence = int(np.clip(required_docs + rng.integers(-3, 2), 0, 10))
        guideline = int(rng.choice([0, 4, 6, 8, 12]))
        therapy_weeks = int(max(0, guideline + rng.integers(-4, 7)))
        case = {
            "case_id": f"SYN-{seed}-{index + 1:04d}",
            "payer": str(rng.choice(PAYER_OPTIONS[:-1])),
            "service_type": str(rng.choice(SERVICE_OPTIONS)),
            "diagnosis_group": str(rng.choice(DIAGNOSIS_OPTIONS)),
            "age_years": int(rng.integers(18, 91)),
            "urgent": bool(rng.random() < 0.16),
            "inpatient": bool(rng.random() < 0.28),
            "prior_auth_required": bool(rng.random() < 0.92),
            "member_eligible": bool(rng.random() < 0.96),
            "in_network": bool(rng.random() < 0.82),
            "requested_units": int(np.clip(rng.gamma(2.0, 6.0), 1, 90)),
            "evidence_count": evidence,
            "required_document_count": required_docs,
            "conservative_therapy_weeks": therapy_weeks,
            "guideline_min_weeks": guideline,
            "failed_conservative_therapy": bool(rng.random() < 0.68),
            "specialist_order": bool(rng.random() < 0.76),
            "estimated_cost": int(np.exp(rng.uniform(np.log(200), np.log(120_000)))),
            "previous_denials": int(np.clip(rng.poisson(0.5), 0, 6)),
            "clinical_notes": "Synthetic de-identified demonstration record generated by AuthGuard.",
            "data_source": "synthetic_demo",
        }
        cases.append(case)
    return cases


def write_live_data_template(path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    cases = generate_synthetic_cases(count=4, seed=2026)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(cases[0].keys()))
        writer.writeheader()
        writer.writerows(cases)
    return destination
