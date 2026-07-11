# BedFlow AI Package Summary

## Current platform capabilities

This package contains the complete BedFlow AI portfolio platform through the production-readiness feature set, including:

- model-scored discharge prioritization with three saved XGBoost models;
- readiness checklists, role-owned tasks, escalation timers, and immutable task events;
- agentic patient-safety and operational-flow review;
- authenticated human decisions and audit export;
- capacity what-if simulation;
- FHIR R4-shaped demonstration export;
- health, readiness, version, metrics, structured logs, CI, secret scanning, and clean packaging;
- persistent JSON runtime storage through `BEDFLOW_DATA_DIR`.

## Persistent JSON deployment

PostgreSQL is intentionally deferred. Mutable records can be placed on a Railway or Docker volume:

```text
BEDFLOW_DATA_DIR=/data
```

Attach the volume at `/data` and keep the application at one replica. Existing mounted files are preserved; missing stores are initialized safely on first startup.

## Operational endpoints

```text
GET /api/health
GET /api/ready
GET /api/system/version
GET /api/metrics        # Administrator only
```

## Local validation

```text
24 automated tests passed
Full backend smoke test passed
Python compilation passed
Persistent-storage initialization tests passed
Clean-package secret scan passed
Zip integrity passed
```

## Remaining priorities

1. Stronger readmission-model validation, calibration, threshold analysis, and patient-group splitting.
2. Formal SHAP patient-level explanations.
3. Screenshots, a short demonstration video, and a GitHub Pages landing page.
4. Optional replacement of synthetic discharge-flow data if a suitable public operational dataset becomes available.
5. Enterprise identity and real EHR integration only if the prototype moves beyond a portfolio demonstration.

## Important limitations

- JSON persistence is designed for one low-traffic application instance, not multiple replicas.
- Request metrics reset when the API process restarts.
- The operational models and simulator use synthetic/proxy data and are not validated for clinical use.
