"""Stage 5 agentic command-center layer for MedPack AI.

Stage 5 is the final portfolio/demo layer.  It does not replace Stages 1-4;
it wraps them into a single incident-command style decision packet with:
- command status and priority
- owner-assigned action cards
- escalation/timing guidance
- executive briefing
- audit/checklist evidence

The calculations are deterministic and local so the demo remains no-freeze and
zero-token by default.  Optional Groq mode can still rewrite the language in the
frontend, but the facts here remain the source of truth.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, Iterable, Mapping, Optional

from backend.traceability import ensure_traceability_fields, load_inventory_state
from backend.task_manager import list_tasks
from backend.stage3_action_plan import build_stage3_action_plan
from backend.stage4_roi import build_stage4_roi_analysis

PLAYBOOK_PATH = "database/escalation_playbooks.json"

DEFAULT_PLAYBOOKS: Dict[str, Any] = {
    "stage": "Stage 5 - Agentic Command Center Playbooks",
    "description": "Demo playbooks for MedPack AI final control-tower decisions. Edit these to match local hospital workflow.",
    "risk_playbooks": {
        "Critical": {
            "priority_code": "P0",
            "command_status": "RED - Command action now",
            "response_window_minutes": 15,
            "primary_owner": "Materials Supervisor",
            "escalation_owner": "Clinical Operations Lead",
            "cadence": "Update every 15 minutes until resolved"
        },
        "High": {
            "priority_code": "P1",
            "command_status": "ORANGE - Act this shift",
            "response_window_minutes": 30,
            "primary_owner": "Supply Tech Lead",
            "escalation_owner": "Charge Nurse",
            "cadence": "Update within 30 minutes"
        },
        "Medium": {
            "priority_code": "P2",
            "command_status": "YELLOW - Preventive action",
            "response_window_minutes": 90,
            "primary_owner": "Warehouse / PAR Tech",
            "escalation_owner": "Supply Chain Coordinator",
            "cadence": "Review during next supply round"
        },
        "Low": {
            "priority_code": "P3",
            "command_status": "GREEN - Monitor",
            "response_window_minutes": 240,
            "primary_owner": "Inventory Analyst",
            "escalation_owner": "None unless trend worsens",
            "cadence": "Monitor next forecast refresh"
        }
    },
    "default_owners": {
        "forecast_validation": "Inventory Analyst",
        "usable_stock_check": "Supply Chain Coordinator",
        "packing": "Warehouse / PAR Tech",
        "transfer": "Supply Tech Lead",
        "supplier_order": "Buyer / Procurement",
        "substitute_review": "Charge Nurse + Supply Chain",
        "waste_rotation": "Materials Supervisor",
        "finance_review": "Operations Manager",
        "escalation": "Clinical Operations Lead"
    }
}


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    return int(round(_as_float(value, float(default))))


def load_stage5_playbooks() -> Dict[str, Any]:
    """Load the editable Stage 5 command-center playbook."""
    if not os.path.exists(PLAYBOOK_PATH):
        return DEFAULT_PLAYBOOKS
    try:
        with open(PLAYBOOK_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            merged = json.loads(json.dumps(DEFAULT_PLAYBOOKS))
            for k, v in data.items():
                if isinstance(v, dict) and isinstance(merged.get(k), dict):
                    merged[k].update(v)
                else:
                    merged[k] = v
            return merged
    except Exception:
        pass
    return DEFAULT_PLAYBOOKS


def _risk_from_inputs(stage3: Mapping[str, Any], stage4: Mapping[str, Any], telemetry: Mapping[str, Any]) -> str:
    risk = str(stage4.get("risk_level") or "").strip()
    if risk:
        return risk
    usable = stage3.get("stage2_usable_stock") or {}
    risk = str(usable.get("risk_level") or (usable.get("shortage_risk_using_usable_stock") or {}).get("risk_level") or "").strip()
    if risk:
        return risk
    true_gap = _as_float(stage3.get("true_shortage_gap"), 0.0)
    forecast = _as_float(stage3.get("predicted_24h_demand") or telemetry.get("predicted_24h_demand"), 0.0)
    coverage_gap_ratio = true_gap / max(forecast, 1.0)
    if true_gap >= 30 or coverage_gap_ratio >= 0.5:
        return "Critical"
    if true_gap >= 15 or coverage_gap_ratio >= 0.25:
        return "High"
    if true_gap > 0:
        return "Medium"
    return "Low"


def _new_card(card_id: str, owner: str, action: str, due_minutes: int, status: str, evidence: str, success_metric: str) -> Dict[str, Any]:
    return {
        "action_id": card_id,
        "owner": owner,
        "action": action,
        "due_minutes": int(max(0, due_minutes)),
        "status": status,
        "evidence": evidence,
        "success_metric": success_metric,
    }


def _build_action_cards(
    telemetry: Mapping[str, Any],
    stage3: Mapping[str, Any],
    stage4: Mapping[str, Any],
    playbook: Mapping[str, Any],
    risk: str,
) -> Dict[str, Any]:
    item = str(telemetry.get("item_name") or stage3.get("item_name") or "Unknown Item")
    dept = str(telemetry.get("department") or stage3.get("department") or "Unknown Department")
    owners = playbook.get("default_owners", {}) or {}
    risk_cfg = (playbook.get("risk_playbooks", {}) or {}).get(risk, (playbook.get("risk_playbooks", {}) or {}).get("Low", {}))
    response_window = _as_int(risk_cfg.get("response_window_minutes"), 60)

    true_gap = max(0.0, _as_float(stage3.get("true_shortage_gap"), 0.0))
    post_transfer_gap = max(0.0, _as_float(stage3.get("post_transfer_gap"), 0.0))
    transfer = stage3.get("transfer_recommendation", {}) or {}
    supplier = stage3.get("supplier_risk", {}) or {}
    substitute = stage3.get("substitute_options", {}) or {}
    stage2 = stage3.get("stage2_usable_stock", {}) or {}
    vendor = supplier.get("recommended_vendor") or {}
    substitute_best = substitute.get("best_substitute_option") or {}
    waste = stage4.get("waste_risk") or {}
    transfer_qty = _as_int(transfer.get("recommended_transfer_qty"), 0)
    order_qty = _as_int(vendor.get("recommended_order_qty"), round(post_transfer_gap)) if post_transfer_gap > 0 else 0
    substitute_qty = _as_int(substitute_best.get("recommended_substitute_qty"), 0) if substitute_best.get("acceptable") else 0
    net_value = _as_float(stage4.get("net_value_estimate"), 0.0)

    cards = []
    cards.append(_new_card(
        "S5-01",
        owners.get("forecast_validation", "Inventory Analyst"),
        f"Validate 24-hour forecast and usable-stock calculation for {item} in {dept}.",
        min(response_window, 30),
        "ready",
        f"Forecast={stage3.get('predicted_24h_demand', 0)}, usable_stock={(stage2 or {}).get('usable_stock', 'N/A')}, true_gap={true_gap}.",
        "Forecast, usable stock, and gap accepted by operations lead."
    ))

    if true_gap <= 0:
        cards.append(_new_card(
            "S5-02",
            owners.get("usable_stock_check", "Supply Chain Coordinator"),
            f"Keep {item} in monitor mode; no emergency packing or ordering is required for {dept} right now.",
            response_window,
            "monitor",
            f"True gap is {true_gap}; Stage 3 best action is {stage3.get('best_action', 'Monitor only')}.",
            "Next forecast refresh still shows no true gap."
        ))
    else:
        if transfer_qty > 0:
            cards.append(_new_card(
                "S5-02",
                owners.get("transfer", "Supply Tech Lead"),
                f"Transfer {transfer_qty} units of {item} into {dept} before ordering emergency stock.",
                min(response_window, 30),
                "action_now" if risk in {"Critical", "High"} else "ready",
                f"Internal transfer can reduce the true gap from {true_gap} to {post_transfer_gap}.",
                f"{transfer_qty} units scanned as DELIVERED to {dept}."
            ))
        pack_qty = max(0, _as_int(stage2.get("recommended_pack_quantity"), _as_int(telemetry.get("recommended_pack_quantity"), round(true_gap))))
        if pack_qty <= 0:
            pack_qty = _as_int(round(max(true_gap - transfer_qty, 0)))
        if pack_qty > 0:
            cards.append(_new_card(
                "S5-03",
                owners.get("packing", "Warehouse / PAR Tech"),
                f"Create/complete packing task for {pack_qty} units of {item} for {dept}.",
                min(response_window, 45),
                "action_now" if risk in {"Critical", "High"} else "ready",
                f"Stage 2/packing logic identified a usable-stock gap of {true_gap}.",
                "Task status reaches PACKED or DELIVERED."
            ))
        if order_qty > 0:
            cards.append(_new_card(
                "S5-04",
                owners.get("supplier_order", "Buyer / Procurement"),
                f"Order {order_qty} units from {vendor.get('vendor_name', 'recommended vendor')} for the remaining post-transfer gap.",
                min(response_window + 30, 120),
                "ready",
                f"Supplier status={supplier.get('supplier_status', 'unknown')}; post-transfer gap={post_transfer_gap}.",
                "PO/rush order created and ETA recorded."
            ))
        if substitute_qty > 0:
            cards.append(_new_card(
                "S5-05",
                owners.get("substitute_review", "Charge Nurse + Supply Chain"),
                f"Hold {substitute_qty} units of {substitute_best.get('substitute_item')} as backup substitute only if approved for the clinical scenario.",
                min(response_window + 15, 90),
                "conditional",
                f"Substitute clinical fit={substitute_best.get('clinical_fit', 'unknown')}.",
                "Clinical owner approves/declines substitute use."
            ))

    waste_units = _as_int(waste.get("waste_risk_units"), 0)
    if waste_units > 0:
        cards.append(_new_card(
            "S5-06",
            owners.get("waste_rotation", "Materials Supervisor"),
            f"Rotate or quarantine {waste_units} units of {item} with expiry/recall/waste exposure.",
            240,
            "waste_control",
            f"Stage 4 waste risk value=${_as_float(waste.get('total_waste_risk_value'), 0.0):,.0f}.",
            "Expiring/recalled lots are rotated, quarantined, or removed."
        ))

    cards.append(_new_card(
        "S5-07",
        owners.get("finance_review", "Operations Manager"),
        f"Review Stage 4 value estimate for this action: net value ${net_value:,.0f}, ROI {stage4.get('roi_ratio', 0)}x.",
        480,
        "executive_review",
        stage4.get("executive_recommendation", "Stage 4 ROI recommendation unavailable."),
        "Executive note accepted for portfolio/demo reporting."
    ))

    if risk in {"Critical", "High"} or (true_gap > 0 and post_transfer_gap > 0 and order_qty <= 0 and substitute_qty <= 0):
        cards.append(_new_card(
            "S5-08",
            owners.get("escalation", "Clinical Operations Lead"),
            f"Escalate unresolved {risk.lower()} supply risk for {item} in {dept}.",
            min(response_window, 30),
            "escalate" if risk == "Critical" else "watch_escalation",
            f"Risk={risk}; true_gap={true_gap}; post_transfer_gap={post_transfer_gap}.",
            "Clinical/supply leader acknowledges risk and fallback plan."
        ))

    open_now = [c for c in cards if c["status"] in {"action_now", "escalate", "ready", "conditional"}]
    return {
        "cards": cards,
        "open_action_count": len(open_now),
        "immediate_action_count": len([c for c in cards if c["status"] in {"action_now", "escalate"}]),
    }


def build_stage5_command_center(
    telemetry: Mapping[str, Any],
    predicted_24h_demand: Optional[float] = None,
    inventory_records: Optional[Iterable[Mapping[str, Any]]] = None,
    tasks: Optional[Iterable[Mapping[str, Any]]] = None,
    stage3_plan: Optional[Mapping[str, Any]] = None,
    stage4_roi: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Return a final Stage 5 command-center decision packet."""
    telemetry = dict(telemetry or {})
    item = str(telemetry.get("item_name") or "Unknown Item")
    dept = str(telemetry.get("department") or "Unknown Department")
    records = [dict(r) for r in (inventory_records if inventory_records is not None else (ensure_traceability_fields() or load_inventory_state(enrich=True)))]
    task_rows = [dict(t) for t in (tasks if tasks is not None else list_tasks(limit=500))]

    if stage3_plan is None:
        stage3_plan = build_stage3_action_plan(
            telemetry,
            predicted_24h_demand=predicted_24h_demand,
            inventory_records=records,
            tasks=task_rows,
        )
    else:
        stage3_plan = dict(stage3_plan)

    if stage4_roi is None:
        stage4_roi = build_stage4_roi_analysis(
            telemetry,
            predicted_24h_demand=predicted_24h_demand,
            inventory_records=records,
            tasks=task_rows,
            stage3_plan=stage3_plan,
        )
    else:
        stage4_roi = dict(stage4_roi)

    playbook = load_stage5_playbooks()
    risk = _risk_from_inputs(stage3_plan, stage4_roi, telemetry)
    risk_cfg = (playbook.get("risk_playbooks", {}) or {}).get(risk, (playbook.get("risk_playbooks", {}) or {}).get("Low", {}))
    priority_code = risk_cfg.get("priority_code", "P3")
    command_status = risk_cfg.get("command_status", "GREEN - Monitor")
    response_window = _as_int(risk_cfg.get("response_window_minutes"), 240)
    primary_owner = risk_cfg.get("primary_owner", "Inventory Analyst")
    escalation_owner = risk_cfg.get("escalation_owner", "None unless trend worsens")

    true_gap = max(0.0, _as_float(stage3_plan.get("true_shortage_gap"), 0.0))
    post_transfer_gap = max(0.0, _as_float(stage3_plan.get("post_transfer_gap"), 0.0))
    net_value = _as_float(stage4_roi.get("net_value_estimate"), 0.0)
    best_action = stage3_plan.get("best_action", "Monitor only")
    final_recommendation = stage3_plan.get("final_recommendation", "No Stage 3 recommendation returned.")
    executive_recommendation = stage4_roi.get("executive_recommendation", "No Stage 4 recommendation returned.")

    card_packet = _build_action_cards(telemetry, stage3_plan, stage4_roi, playbook, risk)
    cards = card_packet["cards"]

    if true_gap <= 0 and risk == "Low":
        headline = f"{item} in {dept} is stable: monitor only."
        commander_decision = f"Keep {item} in green monitor mode. Usable stock covers the 24-hour forecast; no transfer, rush order, or escalation is required."
    elif priority_code in {"P0", "P1"}:
        headline = f"{priority_code} {item} risk in {dept}: execute command-center action now."
        commander_decision = f"Approve the Stage 3 action sequence immediately. {final_recommendation} Financial view: {executive_recommendation}"
    else:
        headline = f"{priority_code} preventive action for {item} in {dept}."
        commander_decision = f"Proceed with the lowest-cost safe action path. {final_recommendation} {executive_recommendation}"

    handoff_packet = {
        "first_15_minutes": [c["action"] for c in cards if c["due_minutes"] <= 15],
        "first_30_minutes": [c["action"] for c in cards if 15 < c["due_minutes"] <= 30],
        "this_shift": [c["action"] for c in cards if 30 < c["due_minutes"] <= 480],
    }

    audit_checklist = [
        {"check": "Forecast reviewed", "status": "ready", "evidence": f"Predicted demand {stage3_plan.get('predicted_24h_demand', stage4_roi.get('predicted_24h_demand', 0))}."},
        {"check": "Usable stock used instead of raw stock", "status": "ready", "evidence": f"True gap {true_gap}; post-transfer gap {post_transfer_gap}."},
        {"check": "Compliance exclusions considered", "status": "ready", "evidence": "Expired/recalled/reserved stock is excluded through Stage 2 logic."},
        {"check": "Transfer/supplier/substitute path evaluated", "status": "ready", "evidence": f"Stage 3 best action: {best_action}."},
        {"check": "Cost/waste/ROI reviewed", "status": "ready", "evidence": f"Net value ${net_value:,.0f}; ROI {stage4_roi.get('roi_ratio', 0)}x."},
    ]

    agent_briefing = {
        "demand_forecast_commander": f"Forecast pressure for {item} in {dept} is mapped to a command priority of {priority_code}. The response window is {response_window} minutes.",
        "inventory_safety_commander": f"Use usable-stock truth, not raw shelf count. Current command risk is {risk}; true shortage gap is {true_gap} units.",
        "supplier_transfer_commander": stage3_plan.get("control_tower_summary", final_recommendation),
        "finance_value_commander": stage4_roi.get("control_tower_summary", executive_recommendation),
        "final_command_center_commander": commander_decision,
    }

    return {
        "stage": "Stage 5 - Agentic Command Center",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "item_name": item,
        "department": dept,
        "priority_code": priority_code,
        "command_status": command_status,
        "risk_level": risk,
        "response_window_minutes": response_window,
        "primary_owner": primary_owner,
        "escalation_owner": escalation_owner,
        "cadence": risk_cfg.get("cadence", "Monitor next forecast refresh"),
        "headline": headline,
        "commander_decision": commander_decision,
        "best_action": best_action,
        "true_shortage_gap": round(true_gap, 2),
        "post_transfer_gap": round(post_transfer_gap, 2),
        "net_value_estimate": round(net_value, 2),
        "roi_ratio": stage4_roi.get("roi_ratio", 0),
        "open_action_count": card_packet["open_action_count"],
        "immediate_action_count": card_packet["immediate_action_count"],
        "action_cards": cards,
        "handoff_packet": handoff_packet,
        "audit_checklist": audit_checklist,
        "agent_briefing": agent_briefing,
        "stage3_action_plan": stage3_plan,
        "stage4_roi_analysis": stage4_roi,
        "control_tower_summary": (
            f"Stage 5 command center: {priority_code} / {command_status} for {item} in {dept}. "
            f"Risk={risk}, true gap={round(true_gap, 2)}, best action={best_action}, net value=${net_value:,.0f}. "
            f"Owner={primary_owner}; escalation={escalation_owner}."
        ),
    }
