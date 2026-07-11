import os
from backend.model import train_model, load_model_and_predict

def test_model_training_and_prediction():
    # Force train model to generate artifact if missing
    model, categories_maps = train_model()
    
    assert os.path.exists("models/supply_demand_xgboost.pkl")
    assert os.path.exists("models/model_metrics.json")
    
    # Test single row prediction
    sample_telemetry = {
        "department": "ICU",
        "item_name": "Oxygen Mask",
        "item_category": "Respiratory",
        "current_stock": 25,
        "patient_volume": 12,
        "acuity_level": 3.5,
        "procedure_count": 5,
        "recent_usage_rate": 6.2,
        "supplier_delay_days": 2.1,
        "day_of_week": 2,
        "hour": 10,
        "season": "Summer",
        "reorder_point": 20,
        "unit_cost": 15.0,
        "supplier_reliability_score": 0.95,
        "pack_time_minutes": 3.5,
        "clinical_criticality": 4
    }
    
    prediction = load_model_and_predict(sample_telemetry)
    assert isinstance(prediction, float)
    assert prediction >= 0.0
