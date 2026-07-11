DEPT_CRITICALITY = {
    "ICU": 5,
    "Emergency Department": 4,
    "Surgery": 4,
    "Labor and Delivery": 3,
    "Med-Surg": 2,
    "Radiology": 2,
    "Outpatient Clinic": 1
}

ACUITY_SCORING = {
    "Low": 1,
    "Medium": 2,
    "High": 3,
    "Critical": 4
}

def calculate_priority_and_pack_quantity(
    item_name,
    department,
    shortage_result,
    telemetry
):
    shortage_gap = shortage_result.get("shortage_gap", 0.0)
    risk_level = shortage_result.get("risk_level", "Low")
    
    # Get parameters
    clinical_criticality = float(telemetry.get("clinical_criticality", 3.0))
    acuity_input = telemetry.get("acuity_level", "Medium")
    
    # acuity_level can be numeric or string
    if isinstance(acuity_input, (int, float)):
        # map float range [1.0, 4.0] to numeric score
        acuity_score = float(acuity_input)
    else:
        acuity_score = float(ACUITY_SCORING.get(acuity_input, 2.0))
        
    supplier_delay_days = float(telemetry.get("supplier_delay_days", 2.0))
    recent_usage_rate = float(telemetry.get("recent_usage_rate", 5.0))
    pack_time_minutes = float(telemetry.get("pack_time_minutes", 5.0))
    
    dept_score = float(DEPT_CRITICALITY.get(department, 2.0))
    
    # Priority Score Formula
    # Higher gap, higher clinical criticality, higher acuity, higher dept importance, higher delay, higher usage -> higher priority.
    # Lower pack time is slightly preferred for quick wins, or maybe higher pack time increases priority if it needs preparation. 
    # Let's subtract pack time to prioritize quick response times, or keep it neutral.
    gap_contribution = max(0.0, shortage_gap) * 1.5
    base_priority = (
        gap_contribution +
        (clinical_criticality * 3.0) +
        (acuity_score * 2.5) +
        (dept_score * 2.5) +
        (supplier_delay_days * 1.0) +
        (recent_usage_rate * 0.2) -
        (pack_time_minutes * 0.1)
    )
    priority_score = max(0.0, round(base_priority, 2))
    
    # Recommended pack quantity
    if risk_level == "Critical":
        buffer = 20
    elif risk_level == "High":
        buffer = 10
    elif risk_level == "Medium":
        buffer = 5
    else:
        buffer = 0
        
    recommended_pack_quantity = int(max(0, round(shortage_gap + buffer)))
    
    escalation_required = False
    if risk_level in ["Critical", "High"] and priority_score > 35:
        escalation_required = True
        
    # Actions
    if recommended_pack_quantity > 0:
        if escalation_required:
            recommended_action = f"IMMEDIATE ESCALATION: Pack {recommended_pack_quantity} units of {item_name} for {department} immediately."
        else:
            recommended_action = f"Replenish: Pack {recommended_pack_quantity} units of {item_name} to restore safe operating stock."
    else:
        recommended_action = f"Monitor: Stock levels of {item_name} in {department} are sufficient. No immediate packing needed."
        
    reasoning = (
        f"Item {item_name} in {department} has a priority score of {priority_score} based on clinical criticality of {clinical_criticality}, "
        f"department score of {dept_score}, and a shortage gap of {shortage_gap:.1f}. Recommended pack quantity is {recommended_pack_quantity} "
        f"including a risk buffer of +{buffer}."
    )
    
    return {
        "priority_score": priority_score,
        "recommended_pack_quantity": recommended_pack_quantity,
        "recommended_action": recommended_action,
        "escalation_required": escalation_required,
        "reasoning": reasoning
    }
