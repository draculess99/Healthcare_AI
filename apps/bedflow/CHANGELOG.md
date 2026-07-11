# Changelog

## Persistent JSON volume support

- Added `BEDFLOW_DATA_DIR` to separate mutable JSON records from static application assets.
- Added first-start seeding for users, tasks, audit records, simulations, access events, and memory files.
- Added atomic memory writes and absolute runtime paths.
- Added Railway and Docker `/data` volume guidance.
- Extended readiness and version output with storage-mode details.
- Kept PostgreSQL out of the portfolio architecture.

## 2026-07-11 — Stage 10A Production Readiness and Observability

### Added

- Structured JSON request logging with route, status, latency, request ID, user, and role context.
- Request ID, response-time, no-sniff, frame, referrer, browser-permission, and sensitive-cache headers.
- `/api/ready`, `/api/system/version`, and administrator-protected `/api/metrics` endpoints.
- System Operations dashboard tab with readiness checks and request diagnostics.
- GitHub Actions CI for secret scanning, compilation, 24 automated tests, smoke checks, and clean packaging.
- Secret-scanning and release-packaging scripts.
- Docker and Railway health-check improvements.
- Stage 10A documentation and six new tests.

### Changed

- `/api/health` is now a lightweight liveness endpoint with app version and Stage 10A status.
- README and roadmap now describe observability, persistent JSON storage, model validation, and portfolio presentation as product capabilities and engineering priorities.

### Remaining limitation

- Runtime records use JSON persistence. Set BEDFLOW_DATA_DIR=/data and attach a volume for restart-safe single-instance deployment; relational storage is intentionally deferred.

## 2026-07-11 — Stage 9 Capacity What-If Simulator

### Added

- Counterfactual operational simulation using the active saved XGBoost artifacts without retraining.
- Pharmacy, insurance, transport, home-care, social-work, Rehab/SNF, case-manager, cleaning-bed, and temporary-bed levers.
- Potential bed recovery, delay-hours removed, High/Critical-case reduction, operational-blocker reduction, and ED boarding-relief estimates.
- Unit-level and patient-level scenario impact tables.
- Signed-user attribution, saved scenario history, and CSV export.
- Stage 9 API endpoints, Streamlit tab, documentation, smoke coverage, and four new automated tests.

### Safety and governance

- Clinical stability, vital-sign stability, and physician sign-off are never automatically cleared by a scenario.
- Scenario outputs are labeled counterfactual synthetic/proxy estimates rather than causal forecasts.
- Bed Manager/Administrator permissions are required to run or save scenarios.

### Fixed

- Patient-task synchronization now requires the `task.sync` permission in both the API and dashboard.
- Model data preparation and artifact-management controls are now permission-aware in the UI and API.

## 2026-07-11 — Model-Scored Command Center & Modernization

### Added

- Batch XGBoost scoring for the complete prioritized discharge queue.
- Cached queue predictions tied to the active model version.
- Delay/readmission probabilities, expected delay hours, model source, version, and prediction timestamps in queue records.
- Leakage-safety tests confirming known outcome columns do not affect inference.
- Reviewer name, role, model version, and UTC timestamp in new audit records.
- Mandatory rationale for override, escalation, and hold decisions.
- Environment-driven API/dashboard configuration.
- Waitress backend launcher support.
- Dockerfile, Railway configuration, Procfile, and `.dockerignore`.
- Expanded unit tests and package `__init__.py` files.

### Changed

- Replaced target-based command-center proxy scoring with saved XGBoost inference.
- Reworked fallback scoring to use only prospective operational inputs.
- Clarified that the unit bed board is simulated/proxy capacity.
- Renamed the dashboard model tab to **Model Quality & Transparency**.
- Added plain-English descriptions of models and saved artifacts.
- Standardized FHIR wording to **FHIR R4-shaped** rather than claiming formal compliance.
- Modernized the README and deployment instructions.

### Security

- Release packages should exclude `.env`, `.git`, caches, and local secrets.

## Stage 8 — Authenticated Role-Based Workflow

- Added local demo users with hashed passwords and signed bearer tokens.
- Added backend permission enforcement for model operations, task ownership, human decisions, audit export, and access-log viewing.
- Bound reviewer identity to the authenticated token instead of trusting UI fields.
- Added role-specific decision options.
- Added immutable task lifecycle events.
- Added administrator CSV audit export and access-event logging.
- Added Streamlit sign-in/sign-out controls and permission-aware actions.
- Added Stage 8 documentation and expanded automated tests to 10 passing tests.
