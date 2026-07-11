import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier, XGBRegressor

from .data_sources import (
    DIABETES_RAW_PATH,
    READMISSION_TRAINING_PATH,
    get_data_sources_summary,
    prepare_diabetes_readmission_data,
)

DATA_PATH = "database/bedflow_patient_data.csv"
METRICS_PATH = "database/model_metrics.json"
METRICS_HISTORY_PATH = "database/model_metrics_history.json"
MODEL_DIR = "models"
MODEL_REGISTRY_PATH = "models/model_registry.json"
FEATURE_COLUMNS_ARTIFACT_PATH = "models/feature_columns.json"
MODEL_CARD_PATH = "models/model_card.md"

MODEL_ARTIFACT_PATHS = {
    "discharge_delay": "models/discharge_delay_xgb.joblib",
    "readmission_risk": "models/readmission_xgb.joblib",
    "expected_delay_hours": "models/delay_hours_xgb.joblib",
}

CATEGORICAL_COLS = [
    "diagnosis_group",
    "acuity_level",
    "mobility_status",
    "home_support_level",
    "discharge_destination",
    "lab_stability_flag",
    "vital_sign_stability_flag",
    "ed_wait_time_pressure",
    "medication_complexity",
]

DROP_COLS = [
    "patient_id",
    "delayed_discharge",
    "readmitted_30_days",
    "expected_discharge_delay_hours",
    "primary_discharge_bottleneck",
]

BINARY_FLAG_LABELS = {
    "lives_alone": "Lives alone",
    "doctor_signoff_pending": "Doctor signoff pending",
    "pharmacy_med_rec_pending": "Pharmacy medication reconciliation pending",
    "transport_pending": "Transport pending",
    "insurance_authorization_pending": "Insurance authorization pending",
    "rehab_snf_placement_pending": "Rehab/SNF placement pending",
    "home_care_setup_pending": "Home-care setup pending",
    "social_work_pending": "Social work review pending",
    "family_pickup_pending": "Family pickup pending",
    "weekend_discharge_flag": "Weekend discharge",
    "after_hours_flag": "After-hours discharge",
    "case_manager_available": "Case manager available",
}

NUMERIC_LABELS = {
    "age": "Age",
    "length_of_stay_days": "Length of stay",
    "prior_admissions_6mo": "Prior admissions in last 6 months",
    "prior_ed_visits_6mo": "Prior ED visits in last 6 months",
    "prior_readmissions_12mo": "Prior readmissions in last 12 months",
    "medication_count": "Medication count",
    "current_bed_occupancy_percent": "Current bed occupancy",
    "ed_boarding_count": "ED boarding count",
}

RISK_FLAG_COLUMNS = {
    "lives_alone",
    "doctor_signoff_pending",
    "pharmacy_med_rec_pending",
    "transport_pending",
    "insurance_authorization_pending",
    "rehab_snf_placement_pending",
    "home_care_setup_pending",
    "social_work_pending",
    "family_pickup_pending",
    "weekend_discharge_flag",
    "after_hours_flag",
}


class BedFlowModels:
    def __init__(self):
        model_params = {
            "n_estimators": 80,
            "max_depth": 3,
            "learning_rate": 0.08,
            "subsample": 0.9,
            "colsample_bytree": 0.9,
            "random_state": 42,
            "n_jobs": 1,
        }
        self.delay_clf = XGBClassifier(eval_metric="logloss", **model_params)
        self.readmission_clf = XGBClassifier(eval_metric="logloss", **model_params)
        self.hours_reg = XGBRegressor(objective="reg:squarederror", **model_params)
        self.is_trained = False
        self.feature_columns: list[str] = []
        self.model_version: str | None = None
        self.training_metadata: dict[str, Any] = {}
        self.loaded_from_artifact = False

        # Stage 5: load the latest approved model artifacts when they exist.
        # If the repo has no artifacts yet, prediction still falls back to training on demand.
        self.load_latest_models(silent=True)

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    def _json_ready(self, value: Any) -> Any:
        """Convert numpy/pandas values into plain JSON-safe Python values."""
        if isinstance(value, dict):
            return {str(k): self._json_ready(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._json_ready(v) for v in value]
        if isinstance(value, tuple):
            return [self._json_ready(v) for v in value]
        if isinstance(value, (np.integer,)):
            return int(value)
        if isinstance(value, (np.floating,)):
            return float(value)
        if isinstance(value, (pd.Timestamp,)):
            return value.isoformat()
        return value

    def _read_json_file(self, path: str, default: Any) -> Any:
        if not os.path.exists(path):
            return default
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return default

    def _write_json_file(self, path: str, payload: Any) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._json_ready(payload), f, indent=4)

    def _dataset_hash(self, path: str = DATA_PATH) -> str:
        if not os.path.exists(path):
            return "missing"
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()[:16]

    def _dataset_summary(self, path: str = DATA_PATH, target_col: str | None = None) -> dict[str, Any]:
        if not os.path.exists(path):
            return {"path": path, "exists": False}
        df = pd.read_csv(path, keep_default_na=False)
        payload: dict[str, Any] = {
            "path": path,
            "exists": True,
            "row_count": int(len(df)),
            "column_count": int(len(df.columns)),
            "dataset_hash": self._dataset_hash(path),
        }
        if target_col and target_col in df.columns:
            payload[f"{target_col}_rate"] = round(
                float(pd.to_numeric(df[target_col], errors="coerce").fillna(0).mean()), 4
            )
        if path == DATA_PATH:
            payload["delayed_discharge_rate"] = round(float(df.get("delayed_discharge", pd.Series(dtype=float)).mean()), 4) if "delayed_discharge" in df else None
            payload["readmission_rate"] = round(float(df.get("readmitted_30_days", pd.Series(dtype=float)).mean()), 4) if "readmitted_30_days" in df else None
        return payload

    def _build_training_metadata(self, metrics: dict[str, Any]) -> dict[str, Any]:
        timestamp = self._now_iso()
        version = f"bedflow-xgb-{timestamp.replace(':', '').replace('-', '').replace('+0000', 'Z')}"
        data_sources = get_data_sources_summary(ensure_readmission=False)
        return {
            "status": "trained",
            "model_version": version,
            "trained_at_utc": timestamp,
            "model_family": "XGBoost",
            "training_mode": "Hybrid Stage 6 training: BedFlow operational data for delay models; public diabetes hospital data for readmission model.",
            "dataset": self._dataset_summary(DATA_PATH),
            "data_sources": data_sources,
            "model_training_sources": {
                "discharge_delay": DATA_PATH,
                "expected_delay_hours": DATA_PATH,
                "readmission_risk": READMISSION_TRAINING_PATH,
                "readmission_raw_public_source": DIABETES_RAW_PATH,
            },
            "feature_count": len(self.feature_columns),
            "feature_columns_path": FEATURE_COLUMNS_ARTIFACT_PATH,
            "artifact_paths": MODEL_ARTIFACT_PATHS,
            "metrics_path": METRICS_PATH,
            "metrics_history_path": METRICS_HISTORY_PATH,
            "model_card_path": MODEL_CARD_PATH,
            "governance_notes": [
                "Stage 6 uses a hybrid data strategy: synthetic/proxy operational data plus public clinical readmission data.",
                "The public dataset is transformed into the BedFlow feature schema and excludes demographic features such as race and gender.",
                "Predictions are decision support only and require human review.",
                "Retraining is explicit through /api/train_models or training/train_models.py; prediction should load saved artifacts when present.",
            ],
        }

    def _write_model_card(self, metadata: dict[str, Any], metrics: dict[str, Any]) -> None:
        os.makedirs(MODEL_DIR, exist_ok=True)
        dataset = metadata.get("dataset", {})
        data_sources = metadata.get("data_sources", {})
        readmission_training = data_sources.get("public_readmission_training_data", {})
        raw_public = data_sources.get("public_readmission_raw_data", {})

        lines = [
            "# BedFlow AI Model Card",
            "",
            f"**Model version:** `{metadata.get('model_version')}`",
            f"**Trained at UTC:** `{metadata.get('trained_at_utc')}`",
            "**Model family:** XGBoost classifiers/regressor",
            "**Stage:** Stage 6 — Public / Realistic Data Upgrade",
            "",
            "## Intended use",
            "",
            "BedFlow AI predicts discharge-delay risk, 30-day readmission risk, and expected discharge-delay hours for a hospital patient-flow demo. It supports human-supervised discharge planning and bed-flow operations. It must not be used as a validated clinical discharge system.",
            "",
            "## Training-data strategy",
            "",
            "Stage 6 uses a hybrid training approach:",
            "",
            f"- **Discharge-delay classifier:** synthetic/proxy BedFlow operations data at `{DATA_PATH}`.",
            f"- **Expected-delay-hours regressor:** synthetic/proxy BedFlow operations data at `{DATA_PATH}`.",
            f"- **30-day readmission classifier:** public diabetes hospital encounter data transformed into BedFlow schema at `{READMISSION_TRAINING_PATH}`.",
            "",
            "The public readmission layer intentionally excludes race and gender from the transformed model features. Operational blockers such as pharmacy, transport, insurance authorization, SNF/Rehab placement, home-care setup, bed occupancy, and ED boarding remain synthetic/proxy operational signals.",
            "",
            "## Dataset snapshots",
            "",
            f"- BedFlow operational rows: `{dataset.get('row_count')}`",
            f"- BedFlow operational columns: `{dataset.get('column_count')}`",
            f"- BedFlow dataset hash: `{dataset.get('dataset_hash')}`",
            f"- Public raw diabetes rows: `{raw_public.get('rows')}`",
            f"- Public raw diabetes hash: `{raw_public.get('hash')}`",
            f"- Processed readmission rows: `{readmission_training.get('rows')}`",
            f"- Processed readmission hash: `{readmission_training.get('hash')}`",
            f"- Processed 30-day readmission rate: `{readmission_training.get('readmitted_30_days_rate')}`",
            f"- Feature count after preprocessing: `{metadata.get('feature_count')}`",
            "",
            "## Artifacts",
            "",
        ]
        for name, path in MODEL_ARTIFACT_PATHS.items():
            lines.append(f"- {name}: `{path}`")
        lines.extend([
            f"- Feature columns: `{FEATURE_COLUMNS_ARTIFACT_PATH}`",
            f"- Metrics: `{METRICS_PATH}`",
            f"- Metrics history: `{METRICS_HISTORY_PATH}`",
            "",
            "## Metrics snapshot",
            "",
            "```json",
            json.dumps(self._json_ready({
                "discharge_delay": metrics.get("discharge_delay"),
                "readmission_risk": metrics.get("readmission_risk"),
                "expected_delay_hours": metrics.get("expected_delay_hours"),
            }), indent=2),
            "```",
            "",
            "## Governance limitations",
            "",
            "- Readmission risk is trained on a public diabetes-focused hospital dataset, so it is still a proxy for a general hospital discharge population.",
            "- Discharge-delay and delay-hours models remain synthetic/proxy operational models.",
            "- Explainability is native feature importance plus patient-specific active signals, not formal SHAP unless added later.",
            "- Human approval, override, hold, or escalation remains mandatory.",
            "- Production deployment would require EHR integration, access controls, clinical validation, monitoring, drift detection, and model-risk governance.",
        ])
        Path(MODEL_CARD_PATH).write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _append_metrics_history(self, metadata: dict[str, Any], metrics: dict[str, Any]) -> None:
        history = self._read_json_file(METRICS_HISTORY_PATH, [])
        if not isinstance(history, list):
            history = []
        history.append({
            "model_version": metadata.get("model_version"),
            "trained_at_utc": metadata.get("trained_at_utc"),
            "dataset_hash": metadata.get("dataset", {}).get("dataset_hash"),
            "feature_count": metadata.get("feature_count"),
            "training_strategy": metadata.get("training_mode"),
            "model_training_sources": metadata.get("model_training_sources"),
            "data_sources": metadata.get("data_sources"),
            "metrics": {
                "discharge_delay": metrics.get("discharge_delay"),
                "readmission_risk": metrics.get("readmission_risk"),
                "expected_delay_hours": metrics.get("expected_delay_hours"),
            },
        })
        self._write_json_file(METRICS_HISTORY_PATH, history[-25:])

    def _save_model_artifacts(self, metrics: dict[str, Any]) -> dict[str, Any]:
        os.makedirs(MODEL_DIR, exist_ok=True)
        metadata = self._build_training_metadata(metrics)

        joblib.dump(self.delay_clf, MODEL_ARTIFACT_PATHS["discharge_delay"])
        joblib.dump(self.readmission_clf, MODEL_ARTIFACT_PATHS["readmission_risk"])
        joblib.dump(self.hours_reg, MODEL_ARTIFACT_PATHS["expected_delay_hours"])
        self._write_json_file(FEATURE_COLUMNS_ARTIFACT_PATH, {
            "model_version": metadata["model_version"],
            "feature_columns": self.feature_columns,
        })
        self._write_json_file(MODEL_REGISTRY_PATH, metadata)
        self._append_metrics_history(metadata, metrics)
        self._write_model_card(metadata, metrics)

        self.model_version = metadata["model_version"]
        self.training_metadata = metadata
        self.loaded_from_artifact = False
        return metadata

    def load_latest_models(self, silent: bool = False) -> dict[str, Any]:
        """Load the latest versioned artifacts from disk.

        Returns a status dictionary. If artifacts are missing, the app remains in
        lazy-training mode and the first prediction can still train on demand.
        """
        registry = self._read_json_file(MODEL_REGISTRY_PATH, {})
        feature_payload = self._read_json_file(FEATURE_COLUMNS_ARTIFACT_PATH, {})
        artifact_paths = registry.get("artifact_paths") or MODEL_ARTIFACT_PATHS
        required_paths = [
            artifact_paths.get("discharge_delay"),
            artifact_paths.get("readmission_risk"),
            artifact_paths.get("expected_delay_hours"),
            FEATURE_COLUMNS_ARTIFACT_PATH,
        ]
        missing = [path for path in required_paths if not path or not os.path.exists(path)]
        if missing:
            status = {
                "status": "missing_artifacts",
                "message": "No complete saved model artifact set was found; will train on demand.",
                "missing_paths": missing,
                "is_trained": self.is_trained,
            }
            if not silent:
                return status
            return status

        self.delay_clf = joblib.load(artifact_paths["discharge_delay"])
        self.readmission_clf = joblib.load(artifact_paths["readmission_risk"])
        self.hours_reg = joblib.load(artifact_paths["expected_delay_hours"])
        self.feature_columns = feature_payload.get("feature_columns", [])
        if not self.feature_columns:
            raise ValueError("Feature column artifact exists but does not contain feature_columns.")
        self.is_trained = True
        self.model_version = registry.get("model_version") or feature_payload.get("model_version")
        self.training_metadata = registry
        self.loaded_from_artifact = True
        return {
            "status": "success",
            "message": "Loaded latest saved BedFlow model artifacts.",
            "model_version": self.model_version,
            "trained_at_utc": registry.get("trained_at_utc"),
            "artifact_paths": artifact_paths,
            "feature_count": len(self.feature_columns),
            "is_trained": self.is_trained,
            "loaded_from_artifact": self.loaded_from_artifact,
        }

    def get_model_governance_summary(self) -> dict[str, Any]:
        registry = self._read_json_file(MODEL_REGISTRY_PATH, {})
        metrics = self._read_json_file(METRICS_PATH, {})
        history = self._read_json_file(METRICS_HISTORY_PATH, [])
        data_sources = get_data_sources_summary(ensure_readmission=False)
        artifact_status = {
            name: {
                "path": path,
                "exists": os.path.exists(path),
                "size_kb": round(os.path.getsize(path) / 1024, 1) if os.path.exists(path) else 0,
            }
            for name, path in MODEL_ARTIFACT_PATHS.items()
        }
        artifact_status["feature_columns"] = {
            "path": FEATURE_COLUMNS_ARTIFACT_PATH,
            "exists": os.path.exists(FEATURE_COLUMNS_ARTIFACT_PATH),
            "size_kb": round(os.path.getsize(FEATURE_COLUMNS_ARTIFACT_PATH) / 1024, 1) if os.path.exists(FEATURE_COLUMNS_ARTIFACT_PATH) else 0,
        }
        return {
            "status": "loaded" if self.is_trained else "not_loaded",
            "active_model_version": self.model_version or registry.get("model_version"),
            "active_source": "saved artifact" if self.loaded_from_artifact else ("in-memory trained model" if self.is_trained else "not trained"),
            "is_trained_in_process": self.is_trained,
            "loaded_from_artifact": self.loaded_from_artifact,
            "registry": registry,
            "artifact_status": artifact_status,
            "feature_count": len(self.feature_columns),
            "metrics_available": bool(metrics),
            "metrics_history_count": len(history) if isinstance(history, list) else 0,
            "latest_history_entry": history[-1] if isinstance(history, list) and history else None,
            "dataset": registry.get("dataset") or self._dataset_summary(),
            "data_sources": registry.get("data_sources") or data_sources,
            "model_training_sources": registry.get("model_training_sources") or {
                "discharge_delay": DATA_PATH,
                "expected_delay_hours": DATA_PATH,
                "readmission_risk": READMISSION_TRAINING_PATH,
                "readmission_raw_public_source": DIABETES_RAW_PATH,
            },
            "model_card_path": MODEL_CARD_PATH,
            "next_governance_steps": [
                "Add authenticated role-based access and backend permission enforcement.",
                "Add approval workflow for promoting model versions.",
                "Add calibration, drift monitoring, subgroup evaluation, and patient-group validation.",
                "Move task, audit, prediction, and memory persistence to PostgreSQL for multi-user deployment.",
            ],
        }

    def _load_encoded_training_data(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        if not os.path.exists(DATA_PATH):
            raise FileNotFoundError(f"Dataset not found at {DATA_PATH}. Run data generator first.")

        df = pd.read_csv(DATA_PATH, keep_default_na=False)
        df_encoded = pd.get_dummies(df, columns=CATEGORICAL_COLS, drop_first=True)
        return df, df_encoded

    def _load_encoded_readmission_training_data(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        if not os.path.exists(READMISSION_TRAINING_PATH):
            prepare_diabetes_readmission_data(force=False)

        if not os.path.exists(READMISSION_TRAINING_PATH):
            # Fallback keeps the demo runnable even if the public dataset was removed.
            df, df_encoded = self._load_encoded_training_data()
            return df, df_encoded

        df = pd.read_csv(READMISSION_TRAINING_PATH, keep_default_na=False)
        df_encoded = pd.get_dummies(df, columns=CATEGORICAL_COLS, drop_first=True)
        return df, df_encoded

    def _build_feature_matrix(self, df_encoded: pd.DataFrame) -> pd.DataFrame:
        X = df_encoded.drop(columns=[col for col in DROP_COLS if col in df_encoded.columns])
        return X.apply(pd.to_numeric, errors="coerce").fillna(0)

    def _align_feature_matrices(self, *matrices: pd.DataFrame) -> list[pd.DataFrame]:
        all_features: list[str] = []
        for matrix in matrices:
            for col in matrix.columns:
                if col not in all_features:
                    all_features.append(col)

        self.feature_columns = all_features
        return [matrix.reindex(columns=self.feature_columns, fill_value=0) for matrix in matrices]

    def train_models(self, persist_artifacts: bool = True):
        _, bedflow_encoded = self._load_encoded_training_data()
        _, readmission_encoded = self._load_encoded_readmission_training_data()

        X_bedflow_raw = self._build_feature_matrix(bedflow_encoded)
        X_readmission_raw = self._build_feature_matrix(readmission_encoded)
        X_bedflow, X_readmission = self._align_feature_matrices(X_bedflow_raw, X_readmission_raw)

        y_delay = pd.to_numeric(bedflow_encoded["delayed_discharge"], errors="coerce").fillna(0).astype(int)
        y_hours = pd.to_numeric(bedflow_encoded["expected_discharge_delay_hours"], errors="coerce").fillna(0)
        y_readmit = pd.to_numeric(readmission_encoded["readmitted_30_days"], errors="coerce").fillna(0).astype(int)

        metrics: dict[str, Any] = {
            "training_strategy": {
                "stage": "Stage 6 — Public / Realistic Data Upgrade",
                "discharge_delay_source": DATA_PATH,
                "expected_delay_hours_source": DATA_PATH,
                "readmission_risk_source": READMISSION_TRAINING_PATH if os.path.exists(READMISSION_TRAINING_PATH) else DATA_PATH,
                "readmission_raw_public_source": DIABETES_RAW_PATH,
                "note": "Readmission risk uses public diabetes hospital encounter data transformed into the BedFlow schema; operational delay models remain synthetic/proxy.",
            }
        }

        # 1. Discharge Delay Risk Model — synthetic/proxy BedFlow operations data
        X_train, X_test, y_train, y_test = train_test_split(X_bedflow, y_delay, test_size=0.2, random_state=42, stratify=y_delay if y_delay.nunique() > 1 else None)
        self.delay_clf.fit(X_train, y_train)
        y_pred = self.delay_clf.predict(X_test)
        y_pred_proba = self.delay_clf.predict_proba(X_test)[:, 1]

        # Baseline: Majority Class
        majority_class = y_train.mode()[0]
        y_base = [majority_class] * len(y_test)

        metrics["discharge_delay"] = {
            "training_source": "Synthetic/proxy BedFlow operations dataset",
            "xgboost": {
                "accuracy": accuracy_score(y_test, y_pred),
                "precision": precision_score(y_test, y_pred, zero_division=0),
                "recall": recall_score(y_test, y_pred, zero_division=0),
                "f1": f1_score(y_test, y_pred, zero_division=0),
                "roc_auc": roc_auc_score(y_test, y_pred_proba),
            },
            "baseline": {
                "accuracy": accuracy_score(y_test, y_base),
                "precision": precision_score(y_test, y_base, zero_division=0),
                "recall": recall_score(y_test, y_base, zero_division=0),
                "f1": f1_score(y_test, y_base, zero_division=0),
            },
        }

        # 2. Readmission Risk Model — public diabetes hospital encounter data transformed into BedFlow schema
        stratify_target = y_readmit if y_readmit.nunique() > 1 else None
        X_train, X_test, y_train, y_test = train_test_split(X_readmission, y_readmit, test_size=0.2, random_state=42, stratify=stratify_target)

        # The public readmission target is naturally imbalanced. Use class weighting
        # and a lower decision threshold for the metrics snapshot so recall is visible
        # in the portfolio dashboard. Patient predictions still expose the raw
        # probability and risk band for human review.
        positive_count = max(int((y_train == 1).sum()), 1)
        negative_count = max(int((y_train == 0).sum()), 1)
        self.readmission_clf.set_params(scale_pos_weight=negative_count / positive_count)
        self.readmission_clf.fit(X_train, y_train)
        y_pred_proba = self.readmission_clf.predict_proba(X_test)[:, 1]
        readmission_decision_threshold = 0.55
        y_pred = (y_pred_proba >= readmission_decision_threshold).astype(int)

        majority_class = y_train.mode()[0]
        y_base = [majority_class] * len(y_test)

        metrics["readmission_risk"] = {
            "training_source": "Public diabetes 130-US hospitals readmission dataset transformed into BedFlow schema",
            "positive_label": "readmitted <30 days",
            "decision_threshold_for_metrics": 0.55,
            "xgboost": {
                "accuracy": accuracy_score(y_test, y_pred),
                "precision": precision_score(y_test, y_pred, zero_division=0),
                "recall": recall_score(y_test, y_pred, zero_division=0),
                "f1": f1_score(y_test, y_pred, zero_division=0),
                "roc_auc": roc_auc_score(y_test, y_pred_proba),
            },
            "baseline": {
                "accuracy": accuracy_score(y_test, y_base),
                "precision": precision_score(y_test, y_base, zero_division=0),
                "recall": recall_score(y_test, y_base, zero_division=0),
                "f1": f1_score(y_test, y_base, zero_division=0),
            },
        }

        # 3. Expected Delay Hours — synthetic/proxy BedFlow operations data
        X_train, X_test, y_train, y_test = train_test_split(X_bedflow, y_hours, test_size=0.2, random_state=42)
        self.hours_reg.fit(X_train, y_train)
        y_pred = self.hours_reg.predict(X_test)

        # Baseline: Median
        median_val = y_train.median()
        y_base = [median_val] * len(y_test)

        metrics["expected_delay_hours"] = {
            "training_source": "Synthetic/proxy BedFlow operations dataset",
            "xgboost": {
                "mae": mean_absolute_error(y_test, y_pred),
                "rmse": np.sqrt(mean_squared_error(y_test, y_pred)),
                "r2": r2_score(y_test, y_pred),
            },
            "baseline": {
                "mae": mean_absolute_error(y_test, y_base),
                "rmse": np.sqrt(mean_squared_error(y_test, y_base)),
                "r2": r2_score(y_test, y_base),
            },
        }

        self.is_trained = True

        # Publish/assign the version before building feature-importance metadata so
        # every metrics section refers to the same active model version.
        if persist_artifacts:
            governance = self._save_model_artifacts(metrics)
        else:
            governance = self._build_training_metadata(metrics)
            self.model_version = governance["model_version"]
            self.training_metadata = governance
            self.loaded_from_artifact = False

        metrics["feature_importance"] = self.get_global_feature_importance(top_n=12)
        metrics["governance"] = governance

        # Save latest metrics snapshot. A separate append-only history is also written when artifacts are persisted.
        self._write_json_file(METRICS_PATH, metrics)

        return self._json_ready(metrics)

    def get_risk_level(self, prob):
        if prob < 0.2:
            return "Low"
        if prob < 0.5:
            return "Medium"
        if prob < 0.8:
            return "High"
        return "Critical"

    def _prepare_patient_features(self, patient_data: dict[str, Any]) -> pd.DataFrame:
        if not self.is_trained:
            self.train_models()

        df = pd.DataFrame([patient_data])

        # Reconstruct dummy columns using the same naming convention as pd.get_dummies.
        for col in CATEGORICAL_COLS:
            if col in df.columns:
                val = df[col].iloc[0]
                dummy_col = f"{col}_{val}"
                df[dummy_col] = 1
                df.drop(columns=[col], inplace=True)

        for col in self.feature_columns:
            if col not in df.columns:
                df[col] = 0

        X = df[self.feature_columns]
        return X.apply(pd.to_numeric, errors="coerce").fillna(0)

    def predict_patient(self, patient_data: dict):
        """Score one patient with the active saved XGBoost model set."""
        if not self.is_trained:
            self.train_models()

        X = self._prepare_patient_features(patient_data)

        delay_prob = float(self.delay_clf.predict_proba(X)[0][1])
        readmit_prob = float(self.readmission_clf.predict_proba(X)[0][1])
        hours_pred = max(0, float(self.hours_reg.predict(X)[0]))

        return {
            "discharge_delay_risk_probability": delay_prob,
            "delay_risk_level": self.get_risk_level(delay_prob),
            "readmission_risk_probability": readmit_prob,
            "readmission_risk_level": self.get_risk_level(readmit_prob),
            "predicted_delay_hours": round(hours_pred, 1),
            "model_version": self.model_version,
            "prediction_source": "saved XGBoost artifacts" if self.loaded_from_artifact else "in-memory XGBoost models",
            "prediction_timestamp_utc": self._now_iso(),
        }

    def predict_dataframe(self, patient_df: pd.DataFrame) -> pd.DataFrame:
        """Batch-score patient rows without retraining the models.

        The command-center queue calls this method once for the complete demo
        patient table, then caches the output. Target/outcome columns are never
        supplied to the models because the matrix is reindexed exclusively to
        the saved feature-column artifact.
        """
        if not self.is_trained:
            self.train_models()
        if patient_df is None or patient_df.empty:
            return pd.DataFrame(columns=[
                "patient_id",
                "discharge_delay_risk_probability",
                "delay_risk_level",
                "readmission_risk_probability",
                "readmission_risk_level",
                "predicted_delay_hours",
                "model_version",
                "prediction_source",
                "prediction_timestamp_utc",
            ])

        working = patient_df.copy()
        patient_ids = (
            working["patient_id"].astype(str).tolist()
            if "patient_id" in working.columns
            else [str(i) for i in working.index]
        )

        categorical = [col for col in CATEGORICAL_COLS if col in working.columns]
        encoded = pd.get_dummies(working, columns=categorical, drop_first=False)
        X = encoded.reindex(columns=self.feature_columns, fill_value=0)
        X = X.apply(pd.to_numeric, errors="coerce").fillna(0)

        delay_probs = self.delay_clf.predict_proba(X)[:, 1].astype(float)
        readmit_probs = self.readmission_clf.predict_proba(X)[:, 1].astype(float)
        delay_hours = np.maximum(0.0, self.hours_reg.predict(X).astype(float))
        timestamp = self._now_iso()
        source = "saved XGBoost artifacts" if self.loaded_from_artifact else "in-memory XGBoost models"

        return pd.DataFrame({
            "patient_id": patient_ids,
            "discharge_delay_risk_probability": delay_probs,
            "delay_risk_level": [self.get_risk_level(float(value)) for value in delay_probs],
            "readmission_risk_probability": readmit_probs,
            "readmission_risk_level": [self.get_risk_level(float(value)) for value in readmit_probs],
            "predicted_delay_hours": np.round(delay_hours, 1),
            "model_version": self.model_version,
            "prediction_source": source,
            "prediction_timestamp_utc": timestamp,
        })

    def _humanize_feature(self, feature: str) -> str:
        for prefix in sorted(CATEGORICAL_COLS, key=len, reverse=True):
            token = f"{prefix}_"
            if feature.startswith(token):
                value = feature[len(token):].replace("_", " ")
                label = prefix.replace("_", " ").title()
                return f"{label}: {value}"
        if feature in BINARY_FLAG_LABELS:
            return BINARY_FLAG_LABELS[feature]
        if feature in NUMERIC_LABELS:
            return NUMERIC_LABELS[feature]
        return feature.replace("_", " ").title()

    def _is_categorical_dummy(self, feature: str) -> bool:
        return any(feature.startswith(f"{prefix}_") for prefix in CATEGORICAL_COLS)

    def _display_value(self, feature: str, value: float, patient_data: dict[str, Any]) -> str:
        if self._is_categorical_dummy(feature):
            return "Selected category"
        raw = patient_data.get(feature, value)
        if feature in RISK_FLAG_COLUMNS or feature == "case_manager_available":
            return "Yes" if int(float(raw or 0)) == 1 else "No"
        if feature == "current_bed_occupancy_percent":
            return f"{float(raw):.0f}%"
        if isinstance(raw, (int, float, np.integer, np.floating)):
            if float(raw).is_integer():
                return str(int(raw))
            return f"{float(raw):.1f}"
        return str(raw)

    def _feature_is_active_signal(self, feature: str, value: float, patient_data: dict[str, Any]) -> bool:
        if self._is_categorical_dummy(feature):
            return float(value) >= 0.5
        raw = patient_data.get(feature, value)
        try:
            numeric = float(raw)
        except (TypeError, ValueError):
            numeric = float(value or 0)

        if feature in RISK_FLAG_COLUMNS:
            return numeric == 1
        if feature == "case_manager_available":
            return numeric == 0
        if feature == "age":
            return numeric >= 65
        if feature == "length_of_stay_days":
            return numeric >= 4
        if feature in {"prior_admissions_6mo", "prior_ed_visits_6mo", "prior_readmissions_12mo"}:
            return numeric > 0
        if feature == "medication_count":
            return numeric >= 8
        if feature == "current_bed_occupancy_percent":
            return numeric >= 85
        if feature == "ed_boarding_count":
            return numeric >= 5
        return numeric != 0

    def _reason_for_feature(self, feature: str, value_display: str, model_key: str) -> str:
        lower = feature.lower()
        target = {
            "discharge_delay": "discharge delay risk",
            "readmission": "readmission risk",
            "delay_hours": "expected delay hours",
        }.get(model_key, "risk")

        if "pharmacy" in lower or "medication" in lower or "med_rec" in lower:
            return f"Medication work can delay discharge and can also affect {target}."
        if "insurance" in lower or "authorization" in lower:
            return f"Insurance authorization is a common discharge blocker, especially for facility transfers."
        if "rehab" in lower or "snf" in lower:
            return f"Rehab/SNF placement creates dependency on facility acceptance, transport, and authorization."
        if "transport" in lower or "family_pickup" in lower:
            return f"Transport readiness determines whether a cleared patient can physically leave the hospital."
        if "home_care" in lower or "home_support" in lower or "lives_alone" in lower:
            return f"Limited home support can make discharge unsafe or require additional case-management coordination."
        if "stable" in lower and "unstable" not in lower:
            return "Clinical stability helps the model distinguish patients who can move through discharge workflow from patients who need safety holds."
        if "lab_stability" in lower or "vital_sign" in lower or "acuity" in lower:
            return "Clinical instability is a hard safety gate before discharge movement should be expedited."
        if "occupancy" in lower or "ed_boarding" in lower or "ed_wait" in lower:
            return f"Hospital capacity pressure increases the operational value of resolving this case quickly."
        if "prior_admissions" in lower or "prior_readmissions" in lower or "prior_ed_visits" in lower:
            return f"Prior utilization history is a proxy for clinical complexity and post-discharge vulnerability."
        if "length_of_stay" in lower:
            return f"Longer stays often indicate a more complex discharge plan and higher coordination burden."
        if "after_hours" in lower or "weekend" in lower:
            return f"After-hours or weekend timing can reduce service availability and slow discharge tasks."
        if "case_manager" in lower:
            return f"Case-manager availability affects the ability to clear insurance, placement, and home-care barriers."
        if "age" in lower:
            return f"Age can correlate with higher coordination needs and post-discharge support requirements."
        return f"This feature had meaningful importance in the trained XGBoost model for {target}."

    def _explain_model(self, model: Any, X: pd.DataFrame, patient_data: dict[str, Any], model_key: str, top_n: int) -> list[dict[str, Any]]:
        importances = getattr(model, "feature_importances_", None)
        if importances is None or len(importances) == 0:
            return []

        rows = []
        for feature, importance in zip(self.feature_columns, importances):
            importance = float(importance or 0)
            if importance <= 0:
                continue
            value = float(X.iloc[0][feature]) if feature in X.columns else 0.0
            active = self._feature_is_active_signal(feature, value, patient_data)

            # Prefer patient-specific active signals, but retain a small fallback weight
            # so the panel can still show global drivers when a patient has few active flags.
            personalized_score = importance * (1.0 if active else 0.25)
            if self._is_categorical_dummy(feature) and not active:
                personalized_score = 0.0
            if feature in RISK_FLAG_COLUMNS and not active:
                personalized_score = 0.0

            if personalized_score <= 0:
                continue

            label = self._humanize_feature(feature)
            value_display = self._display_value(feature, value, patient_data)
            rows.append(
                {
                    "feature": feature,
                    "reason": label,
                    "patient_value": value_display,
                    "model_importance": round(importance, 4),
                    "personalized_score": round(float(personalized_score), 4),
                    "signal_type": "Patient-specific active signal" if active else "Global model driver",
                    "explanation": self._reason_for_feature(feature, value_display, model_key),
                }
            )

        rows.sort(key=lambda item: item["personalized_score"], reverse=True)
        return [dict(row, rank=i + 1) for i, row in enumerate(rows[:top_n])]

    def _model_prediction_label(self, model_key: str, model_outputs: dict[str, Any]) -> str:
        if model_key == "discharge_delay":
            return f"{model_outputs.get('delay_risk_level', 'Unknown')} delay risk ({model_outputs.get('discharge_delay_risk_probability', 0):.2f} probability)"
        if model_key == "readmission":
            return f"{model_outputs.get('readmission_risk_level', 'Unknown')} readmission risk ({model_outputs.get('readmission_risk_probability', 0):.2f} probability)"
        return f"{model_outputs.get('predicted_delay_hours', 0)} predicted delay hours"

    def explain_patient(self, patient_data: dict[str, Any], model_outputs: dict[str, Any] | None = None, top_n: int = 5) -> dict[str, Any]:
        """Return explainability payload for the selected patient.

        This is intentionally dependency-light. It uses XGBoost feature importance
        combined with the selected patient's active feature values. It is not a
        formal SHAP explanation, but it gives a transparent, portfolio-friendly
        risk-reason panel without adding heavy dependencies.
        """
        if not self.is_trained:
            self.train_models()
        X = self._prepare_patient_features(patient_data)
        model_outputs = model_outputs or self.predict_patient(patient_data)
        top_n = max(3, min(int(top_n or 5), 10))

        delay_drivers = self._explain_model(self.delay_clf, X, patient_data, "discharge_delay", top_n)
        readmission_drivers = self._explain_model(self.readmission_clf, X, patient_data, "readmission", top_n)
        hours_drivers = self._explain_model(self.hours_reg, X, patient_data, "delay_hours", top_n)

        dominant_delay = delay_drivers[0]["reason"] if delay_drivers else "the trained discharge-delay model inputs"
        dominant_readmit = readmission_drivers[0]["reason"] if readmission_drivers else "the trained readmission model inputs"
        summary = (
            f"This case is rated {model_outputs.get('delay_risk_level', 'Unknown')} for discharge delay "
            f"and {model_outputs.get('readmission_risk_level', 'Unknown')} for readmission. "
            f"The strongest visible delay driver is {dominant_delay}; the strongest visible readmission driver is {dominant_readmit}."
        )

        return {
            "status": "success",
            "explanation_method": "XGBoost feature-importance + selected-patient active feature values. This is a lightweight explanation, not formal SHAP.",
            "plain_english_summary": summary,
            "discharge_delay": {
                "prediction": self._model_prediction_label("discharge_delay", model_outputs),
                "top_drivers": delay_drivers,
            },
            "readmission_risk": {
                "prediction": self._model_prediction_label("readmission", model_outputs),
                "top_drivers": readmission_drivers,
            },
            "expected_delay_hours": {
                "prediction": self._model_prediction_label("delay_hours", model_outputs),
                "top_drivers": hours_drivers,
            },
            "governance_note": "Use these explanations for decision support and audit review only. They do not replace clinical judgment or validated hospital model governance.",
        }

    def _global_importance_rows(self, model: Any, top_n: int) -> list[dict[str, Any]]:
        importances = getattr(model, "feature_importances_", None)
        if importances is None or len(importances) == 0:
            return []
        rows = [
            {
                "feature": feature,
                "reason": self._humanize_feature(feature),
                "importance": round(float(importance or 0), 4),
            }
            for feature, importance in zip(self.feature_columns, importances)
            if float(importance or 0) > 0
        ]
        rows.sort(key=lambda item: item["importance"], reverse=True)
        return [dict(row, rank=i + 1) for i, row in enumerate(rows[:top_n])]

    def get_global_feature_importance(self, top_n: int = 12) -> dict[str, Any]:
        if not self.is_trained:
            self.train_models()
        top_n = max(3, min(int(top_n or 12), 30))
        return {
            "method": "Native XGBoost feature_importances_ from the active model set. Stage 5 loads saved artifacts when available and falls back to in-process training when needed.",
            "model_version": self.model_version,
            "loaded_from_artifact": self.loaded_from_artifact,
            "discharge_delay": self._global_importance_rows(self.delay_clf, top_n),
            "readmission_risk": self._global_importance_rows(self.readmission_clf, top_n),
            "expected_delay_hours": self._global_importance_rows(self.hours_reg, top_n),
        }


# Singleton instance
bedflow_models = BedFlowModels()
