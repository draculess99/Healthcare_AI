import os
from datetime import datetime, timedelta

DEPARTMENTS = [
    "Emergency Department",
    "ICU",
    "Surgery",
    "Med-Surg",
    "Labor and Delivery",
    "Radiology",
    "Outpatient Clinic"
]

ITEMS = {
    "IV Start Kit": "IV Supplies",
    "Syringe 10ml": "IV Supplies",
    "Nitrile Gloves Medium": "PPE",
    "Nitrile Gloves Large": "PPE",
    "Oxygen Mask": "Respiratory",
    "Wound Care Pack": "Wound Care",
    "Foley Catheter Kit": "Catheterization",
    "Blood Draw Kit": "Lab Supplies",
    "PPE Gown": "PPE",
    "Saline Flush": "IV Supplies",
    "Sterile Gauze": "Wound Care",
    "Surgical Tray": "Surgical Supplies",
    "Nasal Cannula": "Respiratory",
    "Patient Monitoring Leads": "Monitoring"
}

CLINICAL_CRITICALITY_MAP = {
    "IV Start Kit": 3,
    "Syringe 10ml": 3,
    "Nitrile Gloves Medium": 2,
    "Nitrile Gloves Large": 2,
    "Oxygen Mask": 4,
    "Wound Care Pack": 3,
    "Foley Catheter Kit": 3,
    "Blood Draw Kit": 2,
    "PPE Gown": 3,
    "Saline Flush": 2,
    "Sterile Gauze": 2,
    "Surgical Tray": 4,
    "Nasal Cannula": 3,
    "Patient Monitoring Leads": 4
}

def ensure_directories():
    os.makedirs("database/raw", exist_ok=True)
    os.makedirs("database/processed", exist_ok=True)
    os.makedirs("models", exist_ok=True)
    os.makedirs("backend/agents", exist_ok=True)
    os.makedirs("frontend", exist_ok=True)
    os.makedirs("tests", exist_ok=True)
    os.makedirs("database", exist_ok=True)

def generate_synthetic_data(num_rows=2000):
    import pandas as pd
    import numpy as np
    ensure_directories()
    np.random.seed(42)
    
    start_time = datetime.now() - timedelta(days=90)
    timestamps = [start_time + timedelta(hours=int(i)) for i in range(num_rows)]
    
    data = []
    item_names = list(ITEMS.keys())
    
    for ts in timestamps:
        dept = np.random.choice(DEPARTMENTS)
        item = np.random.choice(item_names)
        category = ITEMS[item]
        criticality = CLINICAL_CRITICALITY_MAP[item]
        
        # Patient factors
        patient_volume = int(np.random.poisson(lam=15 if dept in ["Emergency Department", "Med-Surg"] else 8))
        acuity_level = float(np.random.uniform(1.0, 4.0)) # 1 to 4
        procedure_count = int(np.random.poisson(lam=patient_volume * 0.4))
        
        # Supply factors
        recent_usage_rate = float(np.random.uniform(2.0, 15.0))
        reorder_point = int(np.random.randint(10, 50))
        current_stock = int(np.random.randint(5, 100))
        
        supplier_delay_days = float(np.random.uniform(0.5, 7.0))
        supplier_reliability = float(np.random.uniform(0.7, 1.0))
        
        unit_cost = float(np.random.uniform(0.5, 150.0))
        pack_time_minutes = float(np.random.uniform(1.0, 10.0))
        
        # Time factors
        day_of_week = ts.weekday()
        hour = ts.hour
        month = ts.month
        season = "Winter" if month in [12, 1, 2] else "Spring" if month in [3, 4, 5] else "Summer" if month in [6, 7, 8] else "Autumn"
        
        # Demand calculation based on factors + noise
        base_demand = (recent_usage_rate * 0.8) + (patient_volume * acuity_level * 0.15) + (procedure_count * 0.5)
        # Random surge factors
        if dept in ["ICU", "Emergency Department"] and acuity_level > 3.0:
            base_demand *= 1.3
        
        # Random noise
        actual_usage_next_24h = max(0.0, base_demand + np.random.normal(0, 2))
        
        data.append({
            "timestamp": ts.isoformat(),
            "department": dept,
            "item_name": item,
            "item_category": category,
            "current_stock": current_stock,
            "patient_volume": patient_volume,
            "acuity_level": round(acuity_level, 2),
            "procedure_count": procedure_count,
            "recent_usage_rate": round(recent_usage_rate, 2),
            "supplier_delay_days": round(supplier_delay_days, 2),
            "day_of_week": day_of_week,
            "hour": hour,
            "season": season,
            "reorder_point": reorder_point,
            "unit_cost": round(unit_cost, 2),
            "supplier_reliability_score": round(supplier_reliability, 2),
            "pack_time_minutes": round(pack_time_minutes, 2),
            "clinical_criticality": criticality,
            "actual_usage_next_24h": round(actual_usage_next_24h, 2)
        })
        
    df = pd.DataFrame(data)
    processed_path = "database/processed/medpack_training_data.csv"
    df.to_csv(processed_path, index=False)
    return df

def load_or_generate_data():
    import pandas as pd
    import numpy as np
    ensure_directories()
    raw_path = "database/raw/kaggle_hospital_supply_chain.csv"
    processed_path = "database/processed/medpack_training_data.csv"
    
    if os.path.exists(raw_path):
        try:
            raw_df = pd.read_csv(raw_path)
            # Perform column mapping or simple synthesis for missing columns
            # Let's inspect raw_df columns and build a mapper
            mapped_data = []
            np.random.seed(42)
            
            # Map columns where possible, or generate if column missing
            for idx, row in raw_df.iterrows():
                # Extract whatever fields resemble or map them
                # Since we don't know the exact structure, map generic names or fall back
                dept = row.get("department", row.get("dept", np.random.choice(DEPARTMENTS)))
                item = row.get("item_name", row.get("item", row.get("product_name", np.random.choice(list(ITEMS.keys())))))
                category = ITEMS.get(item, row.get("item_category", row.get("category", "General Supplies")))
                current_stock = row.get("current_stock", row.get("stock", np.random.randint(5, 100)))
                
                # Others
                patient_volume = int(row.get("patient_volume", np.random.poisson(10)))
                acuity_level = float(row.get("acuity_level", np.random.uniform(1.0, 4.0)))
                procedure_count = int(row.get("procedure_count", np.random.poisson(4)))
                recent_usage_rate = float(row.get("recent_usage_rate", np.random.uniform(2.0, 15.0)))
                supplier_delay_days = float(row.get("supplier_delay_days", np.random.uniform(0.5, 7.0)))
                day_of_week = int(row.get("day_of_week", np.random.randint(0, 7)))
                hour = int(row.get("hour", np.random.randint(0, 24)))
                season = row.get("season", np.random.choice(["Winter", "Spring", "Summer", "Autumn"]))
                reorder_point = int(row.get("reorder_point", np.random.randint(10, 50)))
                unit_cost = float(row.get("unit_cost", np.random.uniform(0.5, 150.0)))
                supplier_reliability = float(row.get("supplier_reliability_score", np.random.uniform(0.7, 1.0)))
                pack_time_minutes = float(row.get("pack_time_minutes", np.random.uniform(1.0, 10.0)))
                criticality = CLINICAL_CRITICALITY_MAP.get(item, int(row.get("clinical_criticality", 3)))
                actual_usage_next_24h = float(row.get("actual_usage_next_24h", recent_usage_rate * 1.1 + np.random.normal(0, 2)))
                actual_usage_next_24h = max(0.0, actual_usage_next_24h)
                
                mapped_data.append({
                    "timestamp": datetime.now().isoformat(),
                    "department": dept,
                    "item_name": item,
                    "item_category": category,
                    "current_stock": int(current_stock),
                    "patient_volume": int(patient_volume),
                    "acuity_level": round(acuity_level, 2),
                    "procedure_count": int(procedure_count),
                    "recent_usage_rate": round(recent_usage_rate, 2),
                    "supplier_delay_days": round(supplier_delay_days, 2),
                    "day_of_week": day_of_week,
                    "hour": hour,
                    "season": season,
                    "reorder_point": int(reorder_point),
                    "unit_cost": round(unit_cost, 2),
                    "supplier_reliability_score": round(supplier_reliability, 2),
                    "pack_time_minutes": round(pack_time_minutes, 2),
                    "clinical_criticality": criticality,
                    "actual_usage_next_24h": round(actual_usage_next_24h, 2)
                })
            df = pd.DataFrame(mapped_data)
            df.to_csv(processed_path, index=False)
            return df
        except Exception as e:
            print(f"Error loading Kaggle CSV: {e}. Falling back to synthetic.")
            return generate_synthetic_data()
    else:
        if os.path.exists(processed_path):
            return pd.read_csv(processed_path)
        return generate_synthetic_data()

def generate_inventory_state():
    import numpy as np
    ensure_directories()
    # Create inventory_state.json which has a snapshot of current stocks for Streamlit
    import json
    inventory_path = "database/inventory_state.json"
    if os.path.exists(inventory_path):
        return
        
    np.random.seed(42)
    state = []
    item_names = list(ITEMS.keys())
    
    for item in item_names:
        for dept in DEPARTMENTS:
            category = ITEMS[item]
            criticality = CLINICAL_CRITICALITY_MAP[item]
            state.append({
                "item_name": item,
                "department": dept,
                "item_category": category,
                "current_stock": int(np.random.randint(5, 80)),
                "patient_volume": int(np.random.poisson(12)),
                "acuity_level": round(float(np.random.uniform(1.0, 4.0)), 2),
                "procedure_count": int(np.random.poisson(4)),
                "recent_usage_rate": round(float(np.random.uniform(2.0, 15.0)), 2),
                "supplier_delay_days": round(float(np.random.uniform(0.5, 6.0)), 2),
                "season": "Summer",
                "hour": 12,
                "reorder_point": int(np.random.randint(10, 40)),
                "unit_cost": round(float(np.random.uniform(0.5, 100.0)), 2),
                "supplier_reliability_score": round(float(np.random.uniform(0.8, 1.0)), 2),
                "pack_time_minutes": round(float(np.random.uniform(1.0, 8.0)), 2),
                "clinical_criticality": criticality
            })
            
    try:
        from backend.traceability import enrich_inventory_records
        state = enrich_inventory_records(state)
    except Exception:
        pass

    with open(inventory_path, "w") as f:
        json.dump(state, f, indent=2)

if __name__ == "__main__":
    ensure_directories()
    load_or_generate_data()
    generate_inventory_state()
    print("Data loader execution complete.")
