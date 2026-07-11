# MedPack AI Privacy Policy

**Effective Date:** January 1, 2025  
**Last Reviewed:** July 1, 2025  
**Policy ID:** PRIV-001  
**Classification:** Internal — All Staff

---

## 1. Purpose

This policy establishes data-handling, privacy, and confidentiality requirements for the MedPack AI hospital supply-chain decision-support system.

MedPack AI is designed to predict supply shortages, optimize packing priorities, and generate operational recommendations. It does **not** require, collect, or store Protected Health Information (PHI).

---

## 2. Scope

This policy applies to:

- All users of the MedPack AI system, including warehouse staff, supply-chain managers, charge nurses, shift supervisors, and executive leadership.
- All data processed by the MedPack AI backend services, including the Flask API, Streamlit dashboard, machine-learning models, and agentic decision committee.
- All deployment environments: local development, staging, and production (Railway, cloud, or on-premise).

---

## 3. Data Collected

MedPack AI processes **operational supply-chain signals only**:

| Data Category | Examples | PHI? |
|---|---|---|
| Department identifiers | Emergency Department, ICU, OR, NICU | No |
| Supply item metadata | Item name, category, lot number, UDI, barcode | No |
| Inventory metrics | Current stock, reorder point, PAR level | No |
| Operational telemetry | Patient volume, acuity level, procedure count | No |
| Usage patterns | Recent usage rate, historical consumption | No |
| Supplier data | Supplier name, lead time, reliability score | No |
| System events | Scan events, packing tasks, forecast results | No |

**No patient names, medical record numbers, diagnoses, addresses, phone numbers, or individual medical histories are collected or stored.**

---

## 4. Data Retention

- **Forecast events and memory logs** are stored in JSON files (`supply_memory_state.json`, `supply_memory_events.jsonl`) and retained for operational auditing purposes.
- **Inventory state snapshots** (`inventory_state.json`) are refreshed on each data-generation cycle.
- **Model artifacts** (trained XGBoost models) are stored locally and regenerated as needed.
- **RAG index files** (FAISS vector indices) are generated from policy and SOP documents and may be regenerated at any time.

Retention periods should follow the facility's records-management policy. MedPack AI does not enforce automatic data deletion, but all stored data is non-PHI operational data.

---

## 5. Data Access Controls

- **Authentication:** Production deployments should implement role-based access control (RBAC) through the hosting platform.
- **API access:** The Flask API does not include built-in authentication. Production deployments must add authentication middleware or reverse-proxy authorization.
- **Environment variables:** Sensitive configuration (API keys for optional LLM providers like Groq or Gemini) must be stored in environment variables or a secrets manager, never committed to version control.

---

## 6. Third-Party Services

MedPack AI can optionally connect to third-party LLM services (Groq, Google Gemini) for enhanced agentic reasoning. When remote LLM mode is enabled:

- Only operational supply-chain data (department, item, stock levels, forecasts) is sent to the LLM provider.
- No PHI is transmitted.
- Users should review the LLM provider's privacy policy for data-handling commitments.

**By default, MedPack AI runs in local zero-token mode and makes no external API calls.**

---

## 7. Compliance

MedPack AI is designed as a supply-chain decision-support tool. It is **not** a medical device, clinical decision-support system, or electronic health record (EHR).

- **HIPAA:** Because MedPack AI does not process PHI, standard HIPAA data-handling requirements for PHI do not apply to the supply-chain data processed by this system. However, deployment environments should follow institutional HIPAA security policies.
- **FDA:** MedPack AI does not diagnose, treat, or make clinical decisions about patients. It is a supply logistics tool.
- **SOC 2 / ISO 27001:** Production deployments should follow the facility's information-security framework for access control, logging, and incident response.

---

## 8. Incident Response

If a data breach or unauthorized access to the MedPack AI system is suspected:

1. Immediately notify the IT Security team and Supply Chain Director.
2. Isolate the affected system or service.
3. Document the scope of the incident.
4. Follow the facility's incident response plan.
5. Because MedPack AI does not store PHI, HIPAA breach notification requirements for PHI typically do not apply, but consult your compliance officer.

---

## 9. Contact

For questions about this privacy policy or the data practices of MedPack AI, contact:

- **Supply Chain IT Team:** supplychain-it@hospital.example.com
- **Privacy Officer:** privacy@hospital.example.com

---

## 10. Policy Review

This policy is reviewed annually or upon significant changes to the MedPack AI system architecture, data sources, or deployment environment.
