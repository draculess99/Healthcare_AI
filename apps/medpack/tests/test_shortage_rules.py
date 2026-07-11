from backend.shortage_rules import calculate_shortage_risk

def test_shortage_rules_risk_levels():
    # Critical risk case: shortage_gap >= 30
    res_critical = calculate_shortage_risk(predicted_24h_demand=50.0, current_stock=10)
    assert res_critical["risk_level"] == "Critical"
    assert res_critical["shortage_gap"] == 40.0
    
    # Critical risk case: coverage_ratio < 0.50
    res_critical_cov = calculate_shortage_risk(predicted_24h_demand=10.0, current_stock=4)
    assert res_critical_cov["risk_level"] == "Critical"
    
    # High risk case: shortage_gap >= 15 or coverage_ratio < 0.75
    res_high = calculate_shortage_risk(predicted_24h_demand=25.0, current_stock=15)
    assert res_high["risk_level"] == "High"
    
    # Medium risk case: shortage_gap >= 5 or coverage_ratio < 1.00
    res_med = calculate_shortage_risk(predicted_24h_demand=12.0, current_stock=10)
    assert res_med["risk_level"] == "Medium"
    
    # Low risk case: otherwise
    res_low = calculate_shortage_risk(predicted_24h_demand=5.0, current_stock=15)
    assert res_low["risk_level"] == "Low"
