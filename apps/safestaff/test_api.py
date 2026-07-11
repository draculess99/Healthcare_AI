import requests
import json

payload = {
    "department": "Emergency",
    "shift_type": "Morning",
    "acuity_level": 3,
    "required_nurses": 2,
    "patient_volume_multiplier": 1.0,
    "date": "2026-06-23",
    "month": 6,
    "day_of_week": 1,
    "visithour": 12,
    "base_wait_time": 120.0,
    "enable_llm_debate": False
}

try:
    res = requests.post("http://127.0.0.1:5000/api/resolve_shortage", json=payload)
    print("Status:", res.status_code)
    data = res.json()
    if data.get("success"):
        log = data["log"]
        print("Keys in committee_evidence:", list(log.get("committee_evidence", {}).keys()))
        for step in log.get("resolution_steps", []):
            if step["agent"] == "AI Committee Coordinator":
                print("FOUND AI COMMITTEE COORDINATOR STEP!")
                print("Output:", step["output"])
    else:
        print("Error:", data)
except Exception as e:
    print("Request Failed:", e)
