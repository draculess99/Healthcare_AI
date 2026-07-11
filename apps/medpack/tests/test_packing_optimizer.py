from backend.packing_optimizer import calculate_priority_and_pack_quantity

def test_packing_optimizer_calculations():
    shortage_result = {
        "shortage_gap": 25.0,
        "risk_level": "High"
    }
    
    telemetry = {
        "clinical_criticality": 4,
        "acuity_level": "Critical",
        "supplier_delay_days": 3.0,
        "recent_usage_rate": 10.0,
        "pack_time_minutes": 2.0
    }
    
    result = calculate_priority_and_pack_quantity(
        item_name="Oxygen Mask",
        department="ICU",
        shortage_result=shortage_result,
        telemetry=telemetry
    )
    
    assert "priority_score" in result
    assert "recommended_pack_quantity" in result
    assert "recommended_action" in result
    assert "escalation_required" in result
    
    # Check buffering for High risk (+10)
    # shortage_gap (25) + buffer (10) = 35
    assert result["recommended_pack_quantity"] == 35
    assert result["priority_score"] > 0
