"""Data-source preparation and provenance helpers for BedFlow AI.

Stage 6 adds a public clinical readmission data layer using the Diabetes 130-US
Hospitals dataset that is already included in this demo repository. The public
dataset is transformed into the same BedFlow feature schema so the readmission
model can train on realistic clinical encounter data while the discharge-delay
and delay-hours models continue to train on synthetic/proxy hospital operations
data.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

BEDFLOW_DATA_PATH = "database/bedflow_patient_data.csv"
DIABETES_RAW_PATH = "dataset_diabetes/diabetic_data.csv"
READMISSION_TRAINING_PATH = "database/readmission_training_data.csv"

DEATH_OR_HOSPICE_DISPOSITIONS = {11, 13, 14, 19, 20, 21}

BEDFLOW_SCHEMA_COLUMNS = [
    "patient_id",
    "age",
    "diagnosis_group",
    "acuity_level",
    "length_of_stay_days",
    "prior_admissions_6mo",
    "prior_ed_visits_6mo",
    "prior_readmissions_12mo",
    "medication_count",
    "medication_complexity",
    "mobility_status",
    "home_support_level",
    "lives_alone",
    "discharge_destination",
    "doctor_signoff_pending",
    "pharmacy_med_rec_pending",
    "transport_pending",
    "insurance_authorization_pending",
    "rehab_snf_placement_pending",
    "home_care_setup_pending",
    "social_work_pending",
    "family_pickup_pending",
    "lab_stability_flag",
    "vital_sign_stability_flag",
    "current_bed_occupancy_percent",
    "ed_boarding_count",
    "ed_wait_time_pressure",
    "weekend_discharge_flag",
    "after_hours_flag",
    "case_manager_available",
    "delayed_discharge",
    "readmitted_30_days",
    "expected_discharge_delay_hours",
    "primary_discharge_bottleneck",
]


def _file_hash(path: str) -> str:
    if not os.path.exists(path):
        return "missing"
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _safe_numeric(series: pd.Series, default: float = 0.0) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(default)


def _age_midpoint(age_bucket: Any) -> int:
    text = str(age_bucket or "").strip()
    if text.startswith("[") and "-" in text:
        try:
            low = int(text.split("-")[0].replace("[", "").strip())
            high = int(text.split("-")[1].replace(")", "").replace("]", "").strip())
            return int((low + high) / 2)
        except Exception:
            return 65
    return 65


def _diagnosis_group(diag_code: Any) -> str:
    text = str(diag_code or "").strip()
    if not text or text == "?":
        return "General Medicine"

    if text.upper().startswith("V") or text.upper().startswith("E"):
        return "General Medicine"

    try:
        code = float(text)
    except ValueError:
        return "General Medicine"

    # Broad ICD-9 style groupings mapped into the smaller BedFlow category list.
    if 390 <= code <= 459 or code == 785:
        return "Cardiology"
    if 460 <= code <= 519 or code == 786:
        return "Pulmonology"
    if 140 <= code <= 239:
        return "Oncology"
    if 710 <= code <= 739:
        return "Orthopedics"
    if 320 <= code <= 389:
        return "Neurology"
    return "General Medicine"


def _acuity_level(admission_type_id: Any, time_in_hospital: Any, num_medications: Any) -> str:
    adm = int(float(admission_type_id or 0))
    los = float(time_in_hospital or 0)
    meds = float(num_medications or 0)
    if adm in {1, 2, 7} or los >= 8 or meds >= 25:
        return "High"
    if adm == 3 and los <= 3 and meds <= 10:
        return "Low"
    return "Medium"


def _medication_complexity(num_medications: Any) -> str:
    meds = float(num_medications or 0)
    if meds >= 20:
        return "High"
    if meds >= 9:
        return "Medium"
    return "Low"


def _discharge_destination(disposition_id: Any) -> str:
    disp = int(float(disposition_id or 0))
    if disp in {3, 15, 24}:
        return "SNF"
    if disp in {4, 5, 22, 23, 28, 29, 30}:
        return "LTC"
    if disp in {6, 8}:
        return "Home"
    if disp in {2, 10, 16, 17, 27}:
        return "Rehab"
    if disp in {13, 14}:
        return "Hospice"
    return "Home"


def _mobility_status(disposition: str, age: int, los: float) -> str:
    if disposition in {"SNF", "LTC"} or los >= 10:
        return "Bedbound"
    if disposition == "Rehab" or age >= 75:
        return "Assisted"
    return "Independent"


def _home_support_level(disposition: str, age: int, prior_inpatient: float, emergency_visits: float) -> str:
    if disposition in {"SNF", "LTC", "Rehab"}:
        return "Poor"
    if age >= 80 and (prior_inpatient > 0 or emergency_visits > 0):
        return "Fair"
    if age >= 70:
        return "Fair"
    return "Good"


def _lab_stability(row: pd.Series) -> str:
    a1c = str(row.get("A1Cresult", "") or "")
    glucose = str(row.get("max_glu_serum", "") or "")
    los = float(row.get("time_in_hospital", 0) or 0)
    if a1c == ">8" or glucose in {">300", ">200"}:
        return "Unstable"
    if a1c in {"None", "nan", ""} and glucose in {"None", "nan", ""} and los >= 7:
        return "Pending"
    return "Stable"


def _vital_stability(acuity: str, los: float, emergency_visits: float, prior_inpatient: float) -> str:
    if acuity == "High" and (los >= 8 or emergency_visits >= 2 or prior_inpatient >= 2):
        return "Unstable"
    return "Stable"


def _ed_pressure(number_emergency: float, number_inpatient: float) -> str:
    score = number_emergency + number_inpatient
    if score >= 5:
        return "Critical"
    if score >= 3:
        return "High"
    if score >= 1:
        return "Medium"
    return "Low"


def _primary_bottleneck(row: pd.Series) -> str:
    if int(row["rehab_snf_placement_pending"]) == 1:
        return "Rehab/SNF Placement"
    if int(row["insurance_authorization_pending"]) == 1:
        return "Insurance Authorization"
    if int(row["pharmacy_med_rec_pending"]) == 1:
        return "Pharmacy"
    if int(row["home_care_setup_pending"]) == 1:
        return "Home Care"
    if int(row["transport_pending"]) == 1:
        return "Transport"
    return "Clinical Complexity"


def prepare_diabetes_readmission_data(
    raw_path: str = DIABETES_RAW_PATH,
    output_path: str = READMISSION_TRAINING_PATH,
    force: bool = False,
) -> dict[str, Any]:
    """Transform the Diabetes 130-US Hospitals CSV into BedFlow-compatible rows.

    The target is `readmitted_30_days`, where only `<30` is positive. We exclude
    death/hospice dispositions because those encounters are not appropriate for
    a discharge-readmission training target.
    """
    if os.path.exists(output_path) and not force:
        df_existing = pd.read_csv(output_path, keep_default_na=False)
        return {
            "status": "exists",
            "path": output_path,
            "rows": int(len(df_existing)),
            "columns": int(len(df_existing.columns)),
            "readmission_rate": round(float(df_existing["readmitted_30_days"].mean()), 4) if len(df_existing) else 0,
            "source_hash": _file_hash(raw_path),
            "processed_hash": _file_hash(output_path),
        }

    if not os.path.exists(raw_path):
        raise FileNotFoundError(
            f"Public diabetes readmission dataset not found at {raw_path}. "
            "Keep the dataset_diabetes/diabetic_data.csv file or run in synthetic-only mode."
        )

    raw = pd.read_csv(raw_path, keep_default_na=False)
    raw = raw.copy()

    # Clean and filter obvious non-discharge/readmission encounters.
    raw["discharge_disposition_id_num"] = _safe_numeric(raw["discharge_disposition_id"])
    raw = raw[~raw["discharge_disposition_id_num"].astype(int).isin(DEATH_OR_HOSPICE_DISPOSITIONS)]
    raw = raw[raw["gender"].astype(str) != "Unknown/Invalid"]

    rows = []
    for _, src in raw.iterrows():
        age = _age_midpoint(src.get("age"))
        los = float(src.get("time_in_hospital") or 0)
        prior_in = float(src.get("number_inpatient") or 0)
        prior_ed = float(src.get("number_emergency") or 0)
        num_meds = float(src.get("num_medications") or 0)
        diagnosis = _diagnosis_group(src.get("diag_1"))
        acuity = _acuity_level(src.get("admission_type_id"), los, num_meds)
        med_complexity = _medication_complexity(num_meds)
        destination = _discharge_destination(src.get("discharge_disposition_id"))
        mobility = _mobility_status(destination, age, los)
        support = _home_support_level(destination, age, prior_in, prior_ed)
        lab_status = _lab_stability(src)
        vital_status = _vital_stability(acuity, los, prior_ed, prior_in)
        ed_pressure = _ed_pressure(prior_ed, prior_in)

        readmitted_30_days = 1 if str(src.get("readmitted")) == "<30" else 0

        pharmacy_pending = 1 if num_meds >= 18 or med_complexity == "High" else 0
        rehab_pending = 1 if destination in {"SNF", "Rehab", "LTC"} else 0
        insurance_pending = 1 if destination in {"SNF", "Rehab", "LTC"} else 0
        home_care_pending = 1 if destination == "Home" and support in {"Fair", "Poor"} else 0
        transport_pending = 1 if destination in {"SNF", "Rehab", "LTC"} or age >= 80 else 0
        social_work_pending = 1 if support in {"Poor", "None"} or destination in {"SNF", "LTC"} else 0
        family_pickup_pending = 1 if destination == "Home" and age >= 75 else 0
        case_manager_available = 0 if (insurance_pending or rehab_pending or home_care_pending) else 1

        row = {
            "patient_id": f"UCI-DM-{src.get('encounter_id')}",
            "age": age,
            "diagnosis_group": diagnosis,
            "acuity_level": acuity,
            "length_of_stay_days": int(max(1, round(los))),
            "prior_admissions_6mo": int(min(prior_in, 10)),
            "prior_ed_visits_6mo": int(min(prior_ed, 10)),
            "prior_readmissions_12mo": int(min(prior_in, 10)),
            "medication_count": int(num_meds),
            "medication_complexity": med_complexity,
            "mobility_status": mobility,
            "home_support_level": support,
            "lives_alone": 1 if (age >= 75 and support in {"Fair", "Poor"}) else 0,
            "discharge_destination": destination,
            "doctor_signoff_pending": 1 if acuity == "High" and vital_status == "Unstable" else 0,
            "pharmacy_med_rec_pending": pharmacy_pending,
            "transport_pending": transport_pending,
            "insurance_authorization_pending": insurance_pending,
            "rehab_snf_placement_pending": rehab_pending,
            "home_care_setup_pending": home_care_pending,
            "social_work_pending": social_work_pending,
            "family_pickup_pending": family_pickup_pending,
            "lab_stability_flag": lab_status,
            "vital_sign_stability_flag": vital_status,
            "current_bed_occupancy_percent": int(78 + min(17, prior_ed + prior_in + (los // 2))),
            "ed_boarding_count": int(min(15, prior_ed + prior_in)),
            "ed_wait_time_pressure": ed_pressure,
            "weekend_discharge_flag": 0,
            "after_hours_flag": 0,
            "case_manager_available": case_manager_available,
            "delayed_discharge": 1 if los >= 6 or rehab_pending or insurance_pending else 0,
            "readmitted_30_days": readmitted_30_days,
            "expected_discharge_delay_hours": round(float(max(0, (los - 4) * 6 + 8 * rehab_pending + 6 * insurance_pending + 3 * pharmacy_pending)), 1),
        }
        row["primary_discharge_bottleneck"] = _primary_bottleneck(pd.Series(row))
        rows.append(row)

    processed = pd.DataFrame(rows, columns=BEDFLOW_SCHEMA_COLUMNS)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    processed.to_csv(output_path, index=False)

    return {
        "status": "created",
        "path": output_path,
        "rows": int(len(processed)),
        "columns": int(len(processed.columns)),
        "readmission_rate": round(float(processed["readmitted_30_days"].mean()), 4) if len(processed) else 0,
        "source_hash": _file_hash(raw_path),
        "processed_hash": _file_hash(output_path),
    }


def summarize_csv(path: str, target_col: str | None = None) -> dict[str, Any]:
    if not os.path.exists(path):
        return {"path": path, "exists": False}
    df = pd.read_csv(path, keep_default_na=False)
    payload: dict[str, Any] = {
        "path": path,
        "exists": True,
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
        "hash": _file_hash(path),
    }
    if target_col and target_col in df.columns and len(df):
        if target_col == "readmitted":
            payload["readmitted_lt_30_rate"] = round(float((df[target_col].astype(str) == "<30").mean()), 4)
            payload["readmitted_distribution"] = {
                str(k): int(v) for k, v in df[target_col].astype(str).value_counts().to_dict().items()
            }
        else:
            payload[f"{target_col}_rate"] = round(float(pd.to_numeric(df[target_col], errors="coerce").fillna(0).mean()), 4)
    return payload


def get_data_sources_summary(ensure_readmission: bool = False) -> dict[str, Any]:
    if ensure_readmission and os.path.exists(DIABETES_RAW_PATH):
        try:
            prepare_diabetes_readmission_data(force=False)
        except Exception:
            # Summary endpoint should be informative even if preparation fails.
            pass

    return {
        "stage": "Stage 6 — Public / Realistic Data Upgrade",
        "training_strategy": "Hybrid: operational models use synthetic BedFlow data; readmission model uses a public clinical readmission dataset transformed into the BedFlow feature schema.",
        "bedflow_operational_data": summarize_csv(BEDFLOW_DATA_PATH, target_col="delayed_discharge"),
        "public_readmission_raw_data": summarize_csv(DIABETES_RAW_PATH, target_col="readmitted"),
        "public_readmission_training_data": summarize_csv(READMISSION_TRAINING_PATH, target_col="readmitted_30_days"),
        "privacy_note": "No PHI is used. Demographic fields such as race and gender are intentionally not included in the transformed model features.",
        "limitations": [
            "The public diabetes dataset is used only for the readmission-risk training demonstration.",
            "Operational blockers such as pharmacy, transport, insurance, and bed pressure remain synthetic/proxy features.",
            "This is not a clinically validated model and must remain human-supervised decision support.",
        ],
    }
