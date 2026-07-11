import sys
import os
import json
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from frontend.dashboard import _build_tiny_groq_context

telemetry = {
    "item_name": "IV Start Kit",
    "department": "Emergency Department",
}
local_result = {
    "prediction": {"predicted_24h_demand": 14.43},
    "shortage_risk": {"risk_level": "High", "current_stock": 1, "true_shortage_gap": 13.43},
    "packing_priority": {"recommended_action": "Pack Now"},
    "stage3_action_plan": {"best_action": "Transfer 13 units"},
    "committee": {
        "rag_knowledge": "[RAG Document 1]: SOP-101 (IV Kits): In the event of an IV Kit shortage in the Emergency Department (ED), substitute with Pediatric IV Kits (if patient < 40kg) or use Central Line Kits for critical patients. Do not use expired IV Kits under any circumstances."
    }
}

tiny = _build_tiny_groq_context(telemetry, local_result)
print("=== TINY ===")
print(json.dumps(tiny, indent=2))
print("============")
