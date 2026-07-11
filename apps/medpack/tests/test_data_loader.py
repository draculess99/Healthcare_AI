import os
import pandas as pd
from backend.data_loader import load_or_generate_data, ensure_directories

def test_data_loader_creates_dataset():
    ensure_directories()
    df = load_or_generate_data()
    
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    
    required_cols = [
        "timestamp", "department", "item_name", "item_category",
        "current_stock", "patient_volume", "acuity_level", "procedure_count",
        "recent_usage_rate", "supplier_delay_days", "day_of_week", "hour",
        "season", "reorder_point", "unit_cost", "supplier_reliability_score",
        "pack_time_minutes", "clinical_criticality", "actual_usage_next_24h"
    ]
    
    for col in required_cols:
        assert col in df.columns, f"Missing required column: {col}"
        
    assert os.path.exists("database/processed/medpack_training_data.csv")
