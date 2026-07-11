# Research operational modules for bed flow

def evaluate_pharmacy_module(patient_data):
    pending = patient_data.get("pharmacy_med_rec_pending", 0)
    meds = patient_data.get("medication_count", 0)
    complex_meds = patient_data.get("medication_complexity", "Low")
    after_hours = patient_data.get("after_hours_flag", 0)

    if not pending:
        return {"pharmacy_pressure_level": "Low", "pharmacy_delay_reason": "Cleared", "recommended_action": "None"}
    
    if complex_meds == "High" or meds > 10:
        if after_hours:
            return {"pharmacy_pressure_level": "Critical", "pharmacy_delay_reason": "Complex MedRec pending after hours", "recommended_action": "Escalate to on-call pharmacist"}
        return {"pharmacy_pressure_level": "High", "pharmacy_delay_reason": "Complex MedRec pending", "recommended_action": "Flag for priority pharmacy review"}
    
    return {"pharmacy_pressure_level": "Medium", "pharmacy_delay_reason": "Standard MedRec pending", "recommended_action": "Monitor pharmacy queue"}


def evaluate_transport_module(patient_data):
    pending = patient_data.get("transport_pending", 0)
    dest = patient_data.get("discharge_destination", "Home")
    family = patient_data.get("family_pickup_pending", 0)
    after_hours = patient_data.get("after_hours_flag", 0)

    if not pending and not family:
        return {"transport_pressure_level": "Low", "transport_delay_reason": "Cleared", "recommended_action": "None"}
    
    if dest in ["SNF", "Rehab", "LTC"] and pending:
        return {"transport_pressure_level": "High", "transport_delay_reason": "Facility transport pending", "recommended_action": "Verify EMS/Transport ETA"}
        
    if family and after_hours:
        return {"transport_pressure_level": "High", "transport_delay_reason": "Family pickup delayed (after hours)", "recommended_action": "Contact family for ETA or reassess for morning discharge"}

    return {"transport_pressure_level": "Medium", "transport_delay_reason": "Transport/pickup pending", "recommended_action": "Confirm transport arrangements"}


def evaluate_rehab_module(patient_data):
    pending = patient_data.get("rehab_snf_placement_pending", 0)
    dest = patient_data.get("discharge_destination", "Home")
    
    if dest not in ["SNF", "Rehab"]:
        return {"placement_pressure_level": "Low", "placement_delay_reason": "N/A", "recommended_action": "None"}
        
    if not pending:
        return {"placement_pressure_level": "Low", "placement_delay_reason": "Placement secured", "recommended_action": "None"}
        
    return {"placement_pressure_level": "Critical", "placement_delay_reason": "Awaiting bed at facility", "recommended_action": "Escalate to case manager / social work"}


def evaluate_insurance_module(patient_data):
    pending = patient_data.get("insurance_authorization_pending", 0)
    dest = patient_data.get("discharge_destination", "Home")
    rehab_pending = patient_data.get("rehab_snf_placement_pending", 0)
    
    if not pending:
        return {"insurance_pressure_level": "Low", "insurance_delay_reason": "Cleared", "recommended_action": "None"}
        
    if dest in ["SNF", "Rehab"]:
        return {"insurance_pressure_level": "Critical", "insurance_delay_reason": "Facility auth pending", "recommended_action": "Urgent review by utilization management"}
        
    return {"insurance_pressure_level": "Medium", "insurance_delay_reason": "Standard auth pending", "recommended_action": "Check payer portal"}


def evaluate_home_care_module(patient_data):
    pending = patient_data.get("home_care_setup_pending", 0)
    support = patient_data.get("home_support_level", "Good")
    lives_alone = patient_data.get("lives_alone", 0)
    
    if not pending:
        return {"home_care_pressure_level": "Low", "home_care_delay_reason": "Cleared", "recommended_action": "None"}
        
    if support in ["Poor", "None"] or lives_alone:
        return {"home_care_pressure_level": "High", "home_care_delay_reason": "Critical home support needed", "recommended_action": "Expedite home health agency intake"}
        
    return {"home_care_pressure_level": "Medium", "home_care_delay_reason": "Home care setup pending", "recommended_action": "Follow up with agency"}


def evaluate_patient_safety_module(patient_data, model_outputs):
    readmit_prob = model_outputs.get("readmission_risk_probability", 0)
    lab_stab = patient_data.get("lab_stability_flag", "Stable")
    vital_stab = patient_data.get("vital_sign_stability_flag", "Stable")
    
    if vital_stab == "Unstable" or lab_stab == "Unstable":
        return {"patient_safety_level": "Critical", "safety_reason": "Clinical instability", "recommended_action": "Hold discharge for safety. MD review required."}
        
    if readmit_prob > 0.7:
        return {"patient_safety_level": "High", "safety_reason": "High readmission risk", "recommended_action": "Ensure post-discharge appointments and support are locked in."}
        
    return {"patient_safety_level": "Low", "safety_reason": "Stable", "recommended_action": "Proceed with standard discharge"}


def evaluate_bed_capacity_module(patient_data, model_outputs):
    occ = patient_data.get("current_bed_occupancy_percent", 80)
    boarding = patient_data.get("ed_boarding_count", 0)
    delay_hours = model_outputs.get("predicted_delay_hours", 0)
    
    if occ >= 95 or boarding > 10:
        level = "Critical"
        val = "High (Boarding Relief)"
        action = "Prioritize this discharge to open bed for ED boarder"
    elif occ >= 85:
        level = "High"
        val = "Medium"
        action = "Standard progression to free bed"
    else:
        level = "Normal"
        val = "Low"
        action = "Routine discharge"
        
    return {
        "bed_pressure_level": level,
        "estimated_bed_recovery_value": val,
        "ed_boarding_relief_level": level,
        "recommended_action": action
    }

def run_all_modules(patient_data, model_outputs):
    return {
        "pharmacy": evaluate_pharmacy_module(patient_data),
        "transport": evaluate_transport_module(patient_data),
        "rehab": evaluate_rehab_module(patient_data),
        "insurance": evaluate_insurance_module(patient_data),
        "home_care": evaluate_home_care_module(patient_data),
        "safety": evaluate_patient_safety_module(patient_data, model_outputs),
        "bed_capacity": evaluate_bed_capacity_module(patient_data, model_outputs)
    }
