import os
import pandas as pd
import numpy as np
import xgboost as xgb
import catboost as cb
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from sklearn.preprocessing import OneHotEncoder, FunctionTransformer
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
import time

from model import add_derived_features, cyclical_transform, CSV_PATH, get_risk_bands

def test_models():
    df = pd.read_csv(CSV_PATH)
    df = add_derived_features(df)
    
    features = [
        "hospital_name",
        "region",
        "facility_size_beds",
        "month",
        "day_of_week",
        "visithour",
        "urgency_level",
        "nurse_to_patient_ratio",
        "specialist_availability",
        "is_weekend",
        "is_winter",
        "is_peak_hour",
        "staffing_pressure_score",
        "capacity_pressure_score",
        "specialist_gap_flag",
        "peak_hour_staffing_pressure",
        "winter_staffing_pressure",
        "weekend_peak_hour"
    ]
    target = "wait_time"
    
    X = df[features]
    y = df[target]
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    categorical_cols = ["hospital_name", "region"]
    cyclical_cols = ["month", "visithour", "day_of_week"]
    numeric_cols = [f for f in features if f not in categorical_cols + cyclical_cols]
    
    preprocessor = ColumnTransformer(
        transformers=[
            ('cat', OneHotEncoder(handle_unknown='ignore', sparse_output=False), categorical_cols),
            ('cyc', FunctionTransformer(cyclical_transform, validate=True), cyclical_cols),
            ('num', 'passthrough', numeric_cols)
        ]
    )
    
    # 1. XGBoost
    pipeline_xgb = Pipeline(steps=[
        ('preprocessor', preprocessor),
        ('regressor', xgb.XGBRegressor(
            objective='reg:squarederror', n_estimators=500, max_depth=4,
            learning_rate=0.03, subsample=0.8, colsample_bytree=0.8, reg_lambda=2, random_state=42
        ))
    ])
    
    # 3. CatBoost
    pipeline_cb = Pipeline(steps=[
        ('preprocessor', preprocessor),
        ('regressor', cb.CatBoostRegressor(
            iterations=500, depth=4, learning_rate=0.03, 
            subsample=0.8, l2_leaf_reg=2, random_state=42, verbose=0
        ))
    ])
    
    results = []
    actual_bands = get_risk_bands(y_test)
    actual_high_crit = np.isin(actual_bands, ["High", "Critical"])
    
    for name, pipeline in [("XGBoost", pipeline_xgb), ("CatBoost", pipeline_cb)]:
        start_time = time.time()
        pipeline.fit(X_train, y_train)
        train_time = time.time() - start_time
        
        y_pred = pipeline.predict(X_test)
        
        mae = mean_absolute_error(y_test, y_pred)
        r2 = r2_score(y_test, y_pred)
        
        pred_bands = get_risk_bands(y_pred)
        risk_band_accuracy = float(np.mean(actual_bands == pred_bands))
        pred_high_crit = np.isin(pred_bands, ["High", "Critical"])
        recall = float(np.sum(actual_high_crit & pred_high_crit) / np.sum(actual_high_crit)) if np.sum(actual_high_crit) > 0 else 1.0
        
        results.append({
            "Model": name,
            "R2": round(r2, 4),
            "MAE": round(mae, 2),
            "Risk Band Acc": round(risk_band_accuracy, 3),
            "High/Crit Recall": round(recall, 3),
            "Train Time (s)": round(train_time, 2)
        })
        
    print(pd.DataFrame(results).to_markdown(index=False))

if __name__ == "__main__":
    test_models()
