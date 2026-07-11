import os
import sys
import json
import requests
import datetime

def run_smoke_test():
    results = {
        "overall_status": "PASS",
        "timestamp": datetime.datetime.now().isoformat(),
        "tests": [],
        "summary": {"passed": 0, "failed": 0}
    }
    
    def log_test(name, status, details=""):
        results["tests"].append({"test_name": name, "status": status, "details": details})
        if status == "PASS":
            results["summary"]["passed"] += 1
        else:
            results["summary"]["failed"] += 1
            results["overall_status"] = "FAIL"

    base_dir = os.path.dirname(os.path.dirname(__file__))
    if base_dir not in sys.path:
        sys.path.insert(0, base_dir)

    # Check App and Streamlit files
    app_exists = os.path.exists(os.path.join(base_dir, "app.py"))
    dash_exists = os.path.exists(os.path.join(base_dir, "frontend", "dashboard.py"))
    
    log_test("app.py exists", "PASS" if app_exists else "FAIL")
    log_test("dashboard.py exists", "PASS" if dash_exists else "FAIL")
    
    # Try importing Flask backend
    try:
        from backend.server import app
        log_test("Flask backend imports", "PASS")
    except Exception as e:
        log_test("Flask backend imports", "FAIL", str(e))
        
    # Check Required Research Data
    from backend.research_modules import _get_db_path
    for f in ["data_sources.json", "esi_seasonal_patterns.csv", "bed_boarding_pressure.csv", "arrival_surge_pressure.csv", "fast_track_flow.csv"]:
        if os.path.exists(_get_db_path(f)):
            log_test(f"Data File: {f}", "PASS")
        else:
            log_test(f"Data File: {f}", "FAIL", f"Missing {f}")
            
    # Try Committee logic pipeline
    try:
        from backend.research_modules import get_seasonal_esi_pressure, get_bed_boarding_pressure, get_arrival_surge_pressure, get_fast_track_flow_pressure, create_committee_evidence, activate_committee_agents, generate_committee_debate_summary, generate_intervention_plan
        
        m1 = get_seasonal_esi_pressure(1)
        m2 = get_bed_boarding_pressure(1, 1, 18)
        m3 = get_arrival_surge_pressure(1, 1, 18)
        m4 = get_fast_track_flow_pressure(1, 1, 18)
        log_test("Module functions return valid outputs", "PASS")
        
        ev = create_committee_evidence(120.0, "Moderate", m1, m2, m3, m4)
        log_test("committee_evidence created", "PASS")
        
        ag = activate_committee_agents(ev)
        log_test("active agents generated", "PASS")
        
        deb = generate_committee_debate_summary(ev, ag)
        log_test("debate summary generated", "PASS")
        
        plan = generate_intervention_plan(ev)
        log_test("intervention plan generated", "PASS")
        
    except Exception as e:
        log_test("Committee logic pipeline", "FAIL", str(e))

    # Presets validation
    try:
        sys.path.append(os.path.join(base_dir, "frontend"))
        from dashboard import demo_scenarios
        required_presets = [
            "1. Normal Evening Baseline",
            "2. Winter Flu Surge + Staff Call-Out",
            "3. Friday Night Waiting Room Overflow",
            "4. Boarding Gridlock / No Inpatient Beds",
            "5. Night Shift Shortage + High Acuity",
            "6. Mass Casualty Intake / Multi-Ambulance Surge"
        ]
        
        for name in required_presets:
            if name in demo_scenarios:
                log_test(f"Preset exists: {name}", "PASS")
                fields = ["nurse_callout_rate", "patient_inflow_multiplier", "waiting_room_count", 
                          "arrival_surge_multiplier", "ed_occupancy_percent", "boarding_count", "fast_track_open"]
                missing = [f for f in fields if f not in demo_scenarios[name]]
                if not missing:
                    log_test(f"Preset {name} has operational fields", "PASS")
                else:
                    log_test(f"Preset {name} has operational fields", "FAIL", f"Missing fields: {missing}")
            else:
                log_test(f"Preset exists: {name}", "FAIL", f"Missing {name} preset")
                
        # Check severe presets produce expected nurse counts
        from backend.research_modules import get_seasonal_esi_pressure, get_bed_boarding_pressure, get_arrival_surge_pressure, get_fast_track_flow_pressure, create_committee_evidence
        
        preset2 = demo_scenarios["2. Winter Flu Surge + Staff Call-Out"]
        m1 = get_seasonal_esi_pressure(preset2["date"].month, preset_data=preset2)
        m2 = get_bed_boarding_pressure(preset2["date"].month, preset2["date"].weekday(), 18, preset_data=preset2)
        m3 = get_arrival_surge_pressure(preset2["date"].month, preset2["date"].weekday(), 18, preset_data=preset2)
        m4 = get_fast_track_flow_pressure(preset2["date"].month, preset2["date"].weekday(), 18, preset_data=preset2)
        ev2 = create_committee_evidence(120.0, "High", m1, m2, m3, m4, preset_data=preset2)
        
        if ev2["final_additional_nurses_needed"] >= 2:
            log_test("Preset 2 produces at least 2 nurses", "PASS")
        else:
            log_test("Preset 2 produces at least 2 nurses", "FAIL", f"Got {ev2['final_additional_nurses_needed']}")

        preset6 = demo_scenarios["6. Mass Casualty Intake / Multi-Ambulance Surge"]
        m1_6 = get_seasonal_esi_pressure(preset6["date"].month, preset_data=preset6)
        m2_6 = get_bed_boarding_pressure(preset6["date"].month, preset6["date"].weekday(), 21, preset_data=preset6)
        m3_6 = get_arrival_surge_pressure(preset6["date"].month, preset6["date"].weekday(), 21, preset_data=preset6)
        m4_6 = get_fast_track_flow_pressure(preset6["date"].month, preset6["date"].weekday(), 21, preset_data=preset6)
        ev6 = create_committee_evidence(130.0, "High", m1_6, m2_6, m3_6, m4_6, preset_data=preset6)
        
        if ev6["final_additional_nurses_needed"] in [3, 4]:
            log_test("Preset 6 produces 3-4 nurses", "PASS")
        else:
            log_test("Preset 6 produces 3-4 nurses", "FAIL", f"Got {ev6['final_additional_nurses_needed']}")
            
    except Exception as e:
        log_test("Presets validation", "FAIL", str(e))

    output_path = os.path.join(os.path.dirname(__file__), "smoke_test_results.json")
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
        
    print(f"Smoke Test complete. Passed: {results['summary']['passed']}, Failed: {results['summary']['failed']}")
    if results["overall_status"] != "PASS":
        sys.exit(1)

if __name__ == "__main__":
    run_smoke_test()
