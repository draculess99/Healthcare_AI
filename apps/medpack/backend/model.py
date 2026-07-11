import os
import json
from backend.data_loader import load_or_generate_data

MODEL_PATH = "models/supply_demand_xgboost.pkl"
METRICS_PATH = "models/model_metrics.json"

CATEGORICAL_COLS = ["department", "item_name", "item_category", "season"]
NUMERICAL_COLS = [
    "current_stock",
    "patient_volume",
    "acuity_level",
    "procedure_count",
    "recent_usage_rate",
    "supplier_delay_days",
    "day_of_week",
    "hour",
    "reorder_point",
    "supplier_reliability_score",
    "clinical_criticality",
    "pack_time_minutes"
]

class FallbackModel:
    """A deterministic fallback model using recent_usage_rate, patient_volume, acuity_level, procedure_count, and supplier_delay_days."""
    def predict(self, df):
        import numpy as np
        preds = []
        for idx, row in df.iterrows():
            recent_usage = row.get("recent_usage_rate", 5.0)
            volume = row.get("patient_volume", 10.0)
            acuity = row.get("acuity_level", 2.0)
            procedures = row.get("procedure_count", 4.0)
            delay = row.get("supplier_delay_days", 2.0)
            
            # Simple formula
            pred = (recent_usage * 0.8) + (volume * acuity * 0.15) + (procedures * 0.5)
            if delay > 4.0:
                pred += 2.0
            preds.append(max(0.0, float(pred)))
        return np.array(preds)

def preprocess_data(df):
    # Ensure mapping of categories
    # Fill categorical codes
    df_encoded = df.copy()
    categories_maps = {}
    
    for col in CATEGORICAL_COLS:
        df_encoded[col] = df_encoded[col].astype(str)
        unique_vals = sorted(df_encoded[col].unique())
        categories_maps[col] = unique_vals
        # Map values to their index
        val_map = {val: idx for idx, val in enumerate(unique_vals)}
        df_encoded[col] = df_encoded[col].map(val_map)
        
    return df_encoded, categories_maps

def train_model():
    import numpy as np
    import joblib
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
    print("Training supply demand forecasting model...")
    df = load_or_generate_data()
    
    df_encoded, categories_maps = preprocess_data(df)
    
    features = CATEGORICAL_COLS + NUMERICAL_COLS
    X = df_encoded[features]
    y = df_encoded["actual_usage_next_24h"]
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    use_xgb = False
    try:
        import xgboost as xgb
        model = xgb.XGBRegressor(n_estimators=20, max_depth=4, learning_rate=0.1, random_state=42, n_jobs=1, verbosity=0)
        model.fit(X_train, y_train)
        use_xgb = True
        print("Successfully trained XGBoost Regressor.")
    except Exception as e:
        print(f"XGBoost training failed or unavailable ({e}). Falling back to RandomForestRegressor...")
        try:
            from sklearn.ensemble import RandomForestRegressor
            model = RandomForestRegressor(n_estimators=20, max_depth=6, random_state=42, n_jobs=1)
            model.fit(X_train, y_train)
            print("Successfully trained RandomForestRegressor.")
        except Exception as rf_err:
            print(f"RandomForestRegressor training failed ({rf_err}). Using FallbackModel.")
            model = FallbackModel()
            
    # Evaluation
    preds = model.predict(X_test)
    mae = mean_absolute_error(y_test, preds)
    rmse = float(np.sqrt(mean_squared_error(y_test, preds)))
    
    try:
        r2 = r2_score(y_test, preds)
    except:
        r2 = 0.0
        
    metrics = {
        "model_type": "XGBoost Regressor" if use_xgb else type(model).__name__,
        "MAE": round(float(mae), 4),
        "RMSE": round(float(rmse), 4),
        "R2": round(float(r2), 4),
        "training_size": len(df)
    }
    
    # Save model and mapping
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump({
        "model": model,
        "categories_maps": categories_maps,
        "features": features
    }, MODEL_PATH)
    
    with open(METRICS_PATH, "w") as f:
        json.dump(metrics, f, indent=2)
        
    print(f"Model and metrics saved successfully. Metrics: {metrics}")
    return model, categories_maps

_MODEL_CACHE = None

def load_model_and_predict(telemetry):
    """
    Predict actual_usage_next_24h based on input telemetry.
    telemetry should be a dict containing all features.
    """
    import numpy as np
    import pandas as pd
    import joblib
    global _MODEL_CACHE
    if _MODEL_CACHE is None:
        if not os.path.exists(MODEL_PATH):
            model, categories_maps = train_model()
            _MODEL_CACHE = {"model": model, "categories_maps": categories_maps}
        else:
            saved = joblib.load(MODEL_PATH)
            _MODEL_CACHE = {"model": saved["model"], "categories_maps": saved["categories_maps"]}
            
    model = _MODEL_CACHE["model"]
    categories_maps = _MODEL_CACHE["categories_maps"]
        
    # Map categoricals using saved mappings and fill missing features
    mapped_features = {}
    
    for col in CATEGORICAL_COLS:
        val = str(telemetry.get(col, ""))
        val_list = categories_maps.get(col, [])
        if val in val_list:
            mapped_features[col] = float(val_list.index(val))
        else:
            mapped_features[col] = -1.0 # Unseen category value
            
    for col in NUMERICAL_COLS:
        mapped_features[col] = float(telemetry.get(col, 0.0))
            
    df_features = pd.DataFrame([mapped_features])
    
    prediction = model.predict(df_features)[0]
    return max(0.0, float(prediction))

if __name__ == "__main__":
    train_model()
