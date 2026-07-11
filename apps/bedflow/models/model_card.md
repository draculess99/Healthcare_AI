# BedFlow AI Model Card

**Model version:** `bedflow-xgb-20260711T055014Z`
**Trained at UTC:** `2026-07-11T05:50:14+00:00`
**Model family:** XGBoost classifiers/regressor
**Stage:** Stage 6 — Public / Realistic Data Upgrade

## Intended use

BedFlow AI predicts discharge-delay risk, 30-day readmission risk, and expected discharge-delay hours for a hospital patient-flow demo. It supports human-supervised discharge planning and bed-flow operations. It must not be used as a validated clinical discharge system.

## Training-data strategy

Stage 6 uses a hybrid training approach:

- **Discharge-delay classifier:** synthetic/proxy BedFlow operations data at `database/bedflow_patient_data.csv`.
- **Expected-delay-hours regressor:** synthetic/proxy BedFlow operations data at `database/bedflow_patient_data.csv`.
- **30-day readmission classifier:** public diabetes hospital encounter data transformed into BedFlow schema at `database/readmission_training_data.csv`.

The public readmission layer intentionally excludes race and gender from the transformed model features. Operational blockers such as pharmacy, transport, insurance authorization, SNF/Rehab placement, home-care setup, bed occupancy, and ED boarding remain synthetic/proxy operational signals.

## Dataset snapshots

- BedFlow operational rows: `500`
- BedFlow operational columns: `34`
- BedFlow dataset hash: `f3b9d1c407b17d84`
- Public raw diabetes rows: `101766`
- Public raw diabetes hash: `0689e7ec031237dc`
- Processed readmission rows: `99340`
- Processed readmission hash: `afe1ebb76fc9a22d`
- Processed 30-day readmission rate: `0.1139`
- Feature count after preprocessing: `44`

## Artifacts

- discharge_delay: `models/discharge_delay_xgb.joblib`
- readmission_risk: `models/readmission_xgb.joblib`
- expected_delay_hours: `models/delay_hours_xgb.joblib`
- Feature columns: `models/feature_columns.json`
- Metrics: `database/model_metrics.json`
- Metrics history: `database/model_metrics_history.json`

## Metrics snapshot

```json
{
  "discharge_delay": {
    "training_source": "Synthetic/proxy BedFlow operations dataset",
    "xgboost": {
      "accuracy": 0.95,
      "precision": 0.9365079365079365,
      "recall": 0.9833333333333333,
      "f1": 0.959349593495935,
      "roc_auc": 0.9916666666666667
    },
    "baseline": {
      "accuracy": 0.6,
      "precision": 0.6,
      "recall": 1.0,
      "f1": 0.75
    }
  },
  "readmission_risk": {
    "training_source": "Public diabetes 130-US hospitals readmission dataset transformed into BedFlow schema",
    "positive_label": "readmitted <30 days",
    "decision_threshold_for_metrics": 0.55,
    "xgboost": {
      "accuracy": 0.7318804107106905,
      "precision": 0.20229304314030314,
      "recall": 0.46000883782589486,
      "f1": 0.281009582939668,
      "roc_auc": 0.66335284172749
    },
    "baseline": {
      "accuracy": 0.8860982484397021,
      "precision": 0.0,
      "recall": 0.0,
      "f1": 0.0
    }
  },
  "expected_delay_hours": {
    "training_source": "Synthetic/proxy BedFlow operations dataset",
    "xgboost": {
      "mae": 1.8930107555389404,
      "rmse": 2.513287061267117,
      "r2": 0.8707593944004238
    },
    "baseline": {
      "mae": 5.808000000000001,
      "rmse": 7.115321496601542,
      "r2": -0.03586664578065801
    }
  }
}
```

## Governance limitations

- Readmission risk is trained on a public diabetes-focused hospital dataset, so it is still a proxy for a general hospital discharge population.
- Discharge-delay and delay-hours models remain synthetic/proxy operational models.
- Explainability is native feature importance plus patient-specific active signals, not formal SHAP unless added later.
- Human approval, override, hold, or escalation remains mandatory.
- Production deployment would require EHR integration, access controls, clinical validation, monitoring, drift detection, and model-risk governance.
