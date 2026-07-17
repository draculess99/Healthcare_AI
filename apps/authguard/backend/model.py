from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

FEATURE_NAMES = [
    "age_years",
    "urgency_score",
    "inpatient",
    "in_network",
    "evidence_ratio",
    "therapy_gap_weeks",
    "failed_conservative_therapy",
    "specialist_order",
    "log_estimated_cost",
    "previous_denials",
    "requested_units",
    "payer_complexity",
    "service_risk",
    "missing_document_count",
]

PAYER_COMPLEXITY = {
    "Medicare": 0.45,
    "Medicaid": 0.58,
    "Commercial A": 0.50,
    "Commercial B": 0.62,
    "Self Pay": 0.30,
}

SERVICE_RISK = {
    "Advanced Imaging": 0.45,
    "Specialty Medication": 0.72,
    "Surgery": 0.78,
    "DME": 0.52,
    "Rehabilitation": 0.42,
    "Post-Acute Placement": 0.68,
}


def case_to_features(case: dict[str, Any], missing_document_count: int | None = None) -> pd.DataFrame:
    required = max(int(case.get("required_document_count", 0)), 1)
    evidence = int(case.get("evidence_count", 0))
    missing = (
        max(required - evidence, 0)
        if missing_document_count is None
        else int(missing_document_count)
    )
    values = {
        "age_years": float(case.get("age_years", 50)),
        "urgency_score": 1.0 if case.get("urgent", False) else 0.0,
        "inpatient": 1.0 if case.get("inpatient", False) else 0.0,
        "in_network": 1.0 if case.get("in_network", True) else 0.0,
        "evidence_ratio": min(evidence / required, 1.5),
        "therapy_gap_weeks": max(
            float(case.get("guideline_min_weeks", 0))
            - float(case.get("conservative_therapy_weeks", 0)),
            0,
        ),
        "failed_conservative_therapy": 1.0 if case.get("failed_conservative_therapy", False) else 0.0,
        "specialist_order": 1.0 if case.get("specialist_order", False) else 0.0,
        "log_estimated_cost": math.log1p(float(case.get("estimated_cost", 0))),
        "previous_denials": float(case.get("previous_denials", 0)),
        "requested_units": float(case.get("requested_units", 1)),
        "payer_complexity": PAYER_COMPLEXITY.get(str(case.get("payer")), 0.55),
        "service_risk": SERVICE_RISK.get(str(case.get("service_type")), 0.55),
        "missing_document_count": float(missing),
    }
    return pd.DataFrame([[values[name] for name in FEATURE_NAMES]], columns=FEATURE_NAMES)


class DenialRiskModel:
    def __init__(self, model_dir: str | Path | None = None) -> None:
        project_root = Path(__file__).resolve().parents[1]
        self.model_dir = Path(model_dir or project_root / "models")
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.model_path = self.model_dir / "denial_risk_xgboost.joblib"
        self.metrics_path = self.model_dir / "model_metrics.json"
        self.model: XGBClassifier | None = None
        self.metrics: dict[str, Any] = {}
        self._load_or_train()

    def _load_or_train(self) -> None:
        if self.model_path.exists() and self.metrics_path.exists():
            try:
                self.model = joblib.load(self.model_path)
                self.metrics = json.loads(self.metrics_path.read_text(encoding="utf-8"))
                return
            except Exception:
                pass
        self.train()

    def train(self, seed: int = 42, n_rows: int = 2200) -> dict[str, Any]:
        rng = np.random.default_rng(seed)
        X = pd.DataFrame({
            "age_years": rng.integers(18, 91, n_rows),
            "urgency_score": rng.binomial(1, 0.16, n_rows),
            "inpatient": rng.binomial(1, 0.28, n_rows),
            "in_network": rng.binomial(1, 0.82, n_rows),
            "evidence_ratio": np.clip(rng.normal(0.88, 0.28, n_rows), 0, 1.5),
            "therapy_gap_weeks": np.clip(rng.normal(1.2, 2.0, n_rows), 0, 12),
            "failed_conservative_therapy": rng.binomial(1, 0.68, n_rows),
            "specialist_order": rng.binomial(1, 0.76, n_rows),
            "log_estimated_cost": rng.uniform(math.log1p(200), math.log1p(120_000), n_rows),
            "previous_denials": np.clip(rng.poisson(0.5, n_rows), 0, 6),
            "requested_units": np.clip(rng.gamma(2.0, 6.0, n_rows), 1, 90),
            "payer_complexity": rng.uniform(0.30, 0.75, n_rows),
            "service_risk": rng.uniform(0.35, 0.85, n_rows),
            "missing_document_count": np.clip(rng.poisson(1.0, n_rows), 0, 7),
        })
        logits = (
            -2.35
            + 1.35 * (1 - X["in_network"])
            + 1.75 * np.clip(1 - X["evidence_ratio"], 0, 1)
            + 0.30 * X["therapy_gap_weeks"]
            + 0.78 * (1 - X["failed_conservative_therapy"])
            + 0.74 * (1 - X["specialist_order"])
            + 0.18 * X["previous_denials"]
            + 0.42 * X["payer_complexity"]
            + 0.72 * X["service_risk"]
            + 0.32 * X["missing_document_count"]
            + 0.20 * X["urgency_score"]
            + rng.normal(0, 0.58, n_rows)
        )
        probability = 1 / (1 + np.exp(-logits))
        y = rng.binomial(1, probability)
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.22, random_state=seed, stratify=y
        )
        self.model = XGBClassifier(
            n_estimators=170,
            max_depth=4,
            learning_rate=0.055,
            subsample=0.88,
            colsample_bytree=0.88,
            reg_lambda=1.4,
            objective="binary:logistic",
            eval_metric="logloss",
            random_state=seed,
            n_jobs=2,
        )
        self.model.fit(X_train, y_train)
        pred = self.model.predict(X_test)
        prob = self.model.predict_proba(X_test)[:, 1]
        self.metrics = {
            "dataset": "synthetic demonstration training data",
            "rows": n_rows,
            "positive_rate": round(float(np.mean(y)), 4),
            "accuracy": round(float(accuracy_score(y_test, pred)), 4),
            "precision": round(float(precision_score(y_test, pred, zero_division=0)), 4),
            "recall": round(float(recall_score(y_test, pred, zero_division=0)), 4),
            "f1": round(float(f1_score(y_test, pred, zero_division=0)), 4),
            "roc_auc": round(float(roc_auc_score(y_test, prob)), 4),
            "feature_importance": {
                name: round(float(value), 5)
                for name, value in sorted(
                    zip(FEATURE_NAMES, self.model.feature_importances_),
                    key=lambda item: item[1],
                    reverse=True,
                )
            },
            "limitations": [
                "The included model is trained on synthetic proxy outcomes.",
                "It demonstrates workflow integration and must not be used for real coverage decisions.",
                "A production model would require payer-specific labeled outcomes, calibration, bias review, and monitoring.",
            ],
        }
        joblib.dump(self.model, self.model_path)
        self.metrics_path.write_text(json.dumps(self.metrics, indent=2), encoding="utf-8")
        return self.metrics

    def predict(self, case: dict[str, Any], missing_document_count: int = 0) -> dict[str, Any]:
        if self.model is None:
            self._load_or_train()
        assert self.model is not None
        frame = case_to_features(case, missing_document_count)
        probability = float(self.model.predict_proba(frame)[0, 1])
        booster = self.model.get_booster()
        contributions = booster.predict(xgb.DMatrix(frame, feature_names=FEATURE_NAMES), pred_contribs=True)[0]
        signal_pairs = sorted(
            zip(FEATURE_NAMES, contributions[:-1]),
            key=lambda item: abs(float(item[1])),
            reverse=True,
        )[:6]
        if probability < 0.25:
            level = "Low"
        elif probability < 0.55:
            level = "Moderate"
        elif probability < 0.80:
            level = "High"
        else:
            level = "Critical"
        return {
            "denial_probability": round(probability, 4),
            "approval_probability": round(1 - probability, 4),
            "risk_level": level,
            "top_signals": [
                {
                    "feature": name,
                    "contribution": round(float(value), 4),
                    "direction": "raises denial risk" if value > 0 else "reduces denial risk",
                }
                for name, value in signal_pairs
            ],
            "model_type": "XGBoost classifier",
            "model_data": "synthetic demonstration data",
        }
