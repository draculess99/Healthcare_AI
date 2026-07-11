import sys
import os

base_dir = os.path.dirname(os.path.abspath(__file__))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from backend.agents.adk_agents import run_adk_workflow

try:
    res = run_adk_workflow(
        log_id="test",
        shift_type="Morning",
        department="Emergency",
        acuity_level=3,
        required_nurses=1,
        candidates=[{"id": "test", "name": "test", "weekly_hours": 36, "base_rate": 50}],
        patient_volume_multiplier=1.0,
        context={
            "month": 6,
            "day_of_week": 1,
            "visithour": 12,
            "base_wait_time": 120.0,
            "enable_llm_debate": False
        }
    )
    print("Success:", res.get("committee_evidence", {}).keys())
except Exception as e:
    import traceback
    traceback.print_exc()
