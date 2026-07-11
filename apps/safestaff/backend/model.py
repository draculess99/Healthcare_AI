import os
import pickle
import numpy as np
import pandas as pd
import xgboost as xgb
import json
from datetime import datetime
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from sklearn.preprocessing import OneHotEncoder, FunctionTransformer
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from typing import Dict, Any, Tuple
import warnings
warnings.filterwarnings('ignore')
warnings.filterwarnings('ignore')

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(BASE_DIR), "database")
CSV_PATH = os.path.join(DATA_DIR, "er_wait_time.csv")
MODEL_PATH = os.path.join(BASE_DIR, "xgboost_model.pkl")

# In-memory model payload cache for production API calls.
# Avoids re-reading and unpickling xgboost_model.pkl on every /api/predict_wait request.
_MODEL_PAYLOAD_CACHE = {}

def load_model_payload(model_path: str = MODEL_PATH):
    """Load the model payload once and reuse it until the file changes on disk."""
    if not os.path.exists(model_path):
        train_model(CSV_PATH, model_path)

    mtime = os.path.getmtime(model_path)
    cached = _MODEL_PAYLOAD_CACHE.get(model_path)
    if cached and cached.get("mtime") == mtime:
        return cached["payload"]

    with open(model_path, "rb") as f:
        payload = pickle.load(f)

    _MODEL_PAYLOAD_CACHE[model_path] = {"mtime": mtime, "payload": payload}
    return payload

def clear_model_payload_cache():
    """Clear cached model payload after retraining/reset."""
    _MODEL_PAYLOAD_CACHE.clear()

HOSPITALS = [
    "Northside Community Hospital",
    "Riverside Medical Center",
    "St. Jude General Hospital",
    "Valley Health Infirmary",
    "Metro Care Hospital"
]

def generate_synthetic_data(file_path: str = CSV_PATH, num_rows: int = 5000):
    np.random.seed(42)
    
    hospital_choices = np.random.choice(HOSPITALS, size=num_rows)
    regions = np.where(np.isin(hospital_choices, ["Northside Community Hospital", "Metro Care Hospital"]), "Urban", "Rural")
    beds = np.select(
        [hospital_choices == "Metro Care Hospital", hospital_choices == "St. Jude General Hospital", hospital_choices == "Northside Community Hospital"],
        [350, 250, 200],
        default=120
    )
    
    months = np.random.randint(1, 13, size=num_rows)
    day_of_week = np.random.randint(0, 7, size=num_rows)
    visit_hour = np.random.randint(0, 24, size=num_rows)
    urgency_level = np.random.choice([1, 2, 3, 4, 5], p=[0.1, 0.2, 0.4, 0.2, 0.1], size=num_rows)
    specialist_availability = np.random.choice([0, 1], p=[0.3, 0.7], size=num_rows)
    
    base_ratio = np.random.uniform(0.12, 0.35, size=num_rows)
    winter_mask = np.isin(months, [12, 1, 2])
    summer_mask = np.isin(months, [7, 8])
    base_ratio[winter_mask] -= np.random.uniform(0.01, 0.04, size=sum(winter_mask))
    base_ratio[summer_mask] -= np.random.uniform(0.01, 0.03, size=sum(summer_mask))
    nurse_to_patient_ratio = np.clip(base_ratio, 0.08, 0.40)
    
    staffing_effect = 25.0 / (nurse_to_patient_ratio + 0.02)
    urgency_effect = (urgency_level - 1) * 15.0
    
    peak_hours = np.isin(visit_hour, range(14, 23))
    hour_effect = np.where(peak_hours, 30.0, 5.0)
    
    season_effect = np.select(
        [np.isin(months, [12, 1, 2]), np.isin(months, [7, 8])],
        [22.0, 10.0],
        default=0.0
    )
    
    weekend_effect = np.where(np.isin(day_of_week, [5, 6]), 15.0, 0.0)
    bed_effect = (350 - beds) * 0.08
    base_wait = 10.0
    noise = np.random.normal(0, 12, size=num_rows)
    
    wait_time = base_wait + staffing_effect + urgency_effect + hour_effect + season_effect + weekend_effect + bed_effect + noise
    wait_time = np.clip(wait_time, 5.0, 360.0)
    
    satisfaction = np.clip(5.0 - (wait_time / 45.0) + np.random.normal(0, 0.5, size=num_rows), 1.0, 5.0)
    
    df = pd.DataFrame({
        "hospital_name": hospital_choices,
        "region": regions,
        "facility_size_beds": beds,
        "month": months,
        "day_of_week": day_of_week,
        "visithour": visit_hour,
        "urgency_level": urgency_level,
        "nurse_to_patient_ratio": np.round(nurse_to_patient_ratio, 3),
        "specialist_availability": specialist_availability,
        "wait_time": np.round(wait_time, 1),
        "patient_satisfaction": np.round(satisfaction, 1)
    })
    
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    df.to_csv(file_path, index=False)
    print(f"Generated synthetic dataset with {num_rows} records at: {file_path}")

def cyclical_transform(X):
    # Expects columns: [month, visithour, day_of_week]
    out = np.zeros((X.shape[0], 6))
    out[:, 0] = np.sin(2 * np.pi * X[:, 0] / 12)
    out[:, 1] = np.cos(2 * np.pi * X[:, 0] / 12)
    out[:, 2] = np.sin(2 * np.pi * X[:, 1] / 24)
    out[:, 3] = np.cos(2 * np.pi * X[:, 1] / 24)
    out[:, 4] = np.sin(2 * np.pi * X[:, 2] / 7)
    out[:, 5] = np.cos(2 * np.pi * X[:, 2] / 7)
    return out

def add_derived_features(df):
    df = df.copy()
    
    # 5. Temporal and Shift Features
    df['is_weekend'] = df['day_of_week'].isin([5, 6]).astype(int)
    df['is_monday'] = (df['day_of_week'] == 0).astype(int)
    df['is_friday'] = (df['day_of_week'] == 4).astype(int)
    
    # Map months to season (0=Winter, 1=Spring, 2=Summer, 3=Fall)
    # Winter: Dec (12), Jan (1), Feb (2)
    # Spring: Mar (3), Apr (4), May (5)
    # Summer: Jun (6), Jul (7), Aug (8)
    # Fall: Sep (9), Oct (10), Nov (11)
    df['season'] = df['month'].apply(lambda x: 0 if x in [12, 1, 2] else (1 if x in [3, 4, 5] else (2 if x in [6, 7, 8] else 3)))
    df['is_winter'] = (df['season'] == 0).astype(int)
    
    # Shift types: Night (23-6), Morning (7-14), Evening (15-22)
    def get_shift_type(h):
        if h >= 23 or h <= 6: return 0 # Night
        elif 7 <= h <= 14: return 1 # Morning
        else: return 2 # Evening
        
    df['shift_type'] = df['visithour'].apply(get_shift_type)
    df['is_night_shift'] = (df['shift_type'] == 0).astype(int)
    df['is_morning_shift'] = (df['shift_type'] == 1).astype(int)
    df['is_afternoon_shift'] = df['visithour'].between(12, 16).astype(int)
    df['is_evening_shift'] = (df['shift_type'] == 2).astype(int)
    
    df['is_shift_change_window'] = df['visithour'].isin([7, 15, 23]).astype(int)
    df['is_peak_hour'] = df['visithour'].between(14, 22).astype(int)
    
    # 6. Operational Interaction Features
    df['staffing_pressure_score'] = 1 / (df['nurse_to_patient_ratio'] + 0.01)
    df['capacity_pressure_score'] = df['staffing_pressure_score'] / (df['facility_size_beds'] + 1)
    df['specialist_gap_flag'] = (df['specialist_availability'] == 0).astype(int)
    
    df['urgency_staffing_pressure'] = df['urgency_level'] * df['staffing_pressure_score']
    df['urgency_specialist_gap'] = df['urgency_level'] * df['specialist_gap_flag']
    df['urgency_off_hours_pressure'] = df['urgency_level'] * df['is_night_shift']
    df['urgency_facility_pressure'] = df['urgency_level'] / (df['facility_size_beds'] + 1)
    
    df['peak_hour_staffing_pressure'] = df['is_peak_hour'] * df['staffing_pressure_score']
    df['weekend_peak_hour'] = df['is_weekend'] * df['is_peak_hour']
    df['winter_staffing_pressure'] = df['is_winter'] * df['staffing_pressure_score']
    df['specialist_strain'] = df['specialist_gap_flag'] * df['staffing_pressure_score']
    df['off_hours_severity'] = df['is_night_shift'] * df['urgency_level']
    
    # 7. Facility and Regional Context
    # Size tier: Small < 100, Medium 100-249, Large 250+
    def get_size_tier(beds):
        if beds < 100: return 0
        elif beds < 250: return 1
        else: return 2
        
    df['size_tier'] = df['facility_size_beds'].apply(get_size_tier)
    df['small_facility_flag'] = (df['size_tier'] == 0).astype(int)
    df['large_facility_flag'] = (df['size_tier'] == 2).astype(int)
    df['specialist_per_bed_pressure'] = df['specialist_availability'] / (df['facility_size_beds'] + 1)
    
    # (Optional based on region values)
    df['rural_specialist_gap'] = ((df['region'] == 'Rural') & (df['specialist_gap_flag'] == 1)).astype(int)
    df['urban_peak_pressure'] = ((df['region'] == 'Urban') & (df['is_peak_hour'] == 1)).astype(int)

    return df

def get_risk_bands(wait_times):
    bands = []
    for w in wait_times:
        if w < 45: bands.append("Low")
        elif w < 90: bands.append("Moderate")
        elif w < 150: bands.append("High")
        else: bands.append("Critical")
    return np.array(bands)

def train_model(csv_path: str = CSV_PATH, model_path: str = MODEL_PATH) -> Tuple[float, float]:
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Data file not found at {csv_path}. Please place the Kaggle dataset 'er_wait_time_real.csv' in the database folder.")
        
    df = pd.read_csv(csv_path)
    
    # MLOps Continuous Retraining logic
    live_csv_path = os.path.join(DATA_DIR, "live_collected_data.csv")
    if os.path.exists(live_csv_path):
        try:
            live_df = pd.read_csv(live_csv_path)
            # Ensure columns match, if live_df has extra/missing it will align
            df = pd.concat([df, live_df], ignore_index=True)
            print(f"Appended {len(live_df)} live collected records to training data.")
        except Exception as e:
            print(f"Error loading live data: {e}")
            
    df = add_derived_features(df)
    
    features = [
        "hospital_name", "region", "facility_size_beds", "month", "day_of_week", 
        "visithour", "urgency_level", "nurse_to_patient_ratio", "specialist_availability",
        "is_weekend", "is_monday", "is_friday", "season", "is_winter", "shift_type",
        "is_night_shift", "is_morning_shift", "is_afternoon_shift", "is_evening_shift",
        "is_shift_change_window", "is_peak_hour", "staffing_pressure_score",
        "capacity_pressure_score", "specialist_gap_flag", "urgency_staffing_pressure",
        "urgency_specialist_gap", "urgency_off_hours_pressure", "urgency_facility_pressure",
        "peak_hour_staffing_pressure", "weekend_peak_hour", "winter_staffing_pressure",
        "specialist_strain", "off_hours_severity", "size_tier", "small_facility_flag",
        "large_facility_flag", "specialist_per_bed_pressure", "rural_specialist_gap",
        "urban_peak_pressure",
        "hospital_historical_avg_wait", "hospital_hour_historical_avg_wait",
        "region_historical_avg_wait", "region_hour_historical_avg_wait"
    ]
    target = "wait_time"
    
    X = df.drop(columns=[target, "patient_satisfaction", "Time to Registration (min)", "Time to Triage (min)", "Time to Medical Professional (min)", "Total Wait Time (min)", "Patient Outcome"], errors="ignore")
    # Make sure target isn't leaked
    y = df[target]
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # 8. Safe Historical Average Features without leakage
    global_mean = y_train.mean()
    
    # Calculate means from training set
    train_df = X_train.copy()
    train_df['target'] = y_train
    
    hosp_mean = train_df.groupby("hospital_name")['target'].mean().to_dict()
    hosp_hour_mean = train_df.groupby(["hospital_name", "visithour"])['target'].mean().to_dict()
    reg_mean = train_df.groupby("region")['target'].mean().to_dict()
    reg_hour_mean = train_df.groupby(["region", "visithour"])['target'].mean().to_dict()
    
    def apply_historical(data):
        d = data.copy()
        d['hospital_historical_avg_wait'] = d['hospital_name'].map(hosp_mean).fillna(global_mean)
        d['hospital_hour_historical_avg_wait'] = d.apply(lambda row: hosp_hour_mean.get((row['hospital_name'], row['visithour']), global_mean), axis=1)
        d['region_historical_avg_wait'] = d['region'].map(reg_mean).fillna(global_mean)
        d['region_hour_historical_avg_wait'] = d.apply(lambda row: reg_hour_mean.get((row['region'], row['visithour']), global_mean), axis=1)
        return d
        
    X_train = apply_historical(X_train)
    X_test = apply_historical(X_test)
    
    # Keep only defined features
    X_train = X_train[features]
    X_test = X_test[features]
    
    categorical_cols = ["hospital_name", "region", "season", "shift_type", "size_tier"]
    cyclical_cols = ["month", "visithour", "day_of_week"]
    numeric_cols = [f for f in features if f not in categorical_cols + cyclical_cols]
    
    preprocessor = ColumnTransformer(
        transformers=[
            ('cat', OneHotEncoder(handle_unknown='ignore', sparse_output=False), categorical_cols),
            ('cyc', FunctionTransformer(cyclical_transform, validate=True), cyclical_cols),
            ('num', 'passthrough', numeric_cols)
        ]
    )
    
    pipeline = Pipeline(steps=[
        ('preprocessor', preprocessor),
        ('regressor', xgb.XGBRegressor(
            objective='reg:squarederror',
            n_estimators=500,
            max_depth=4,
            learning_rate=0.03,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_lambda=2,
            random_state=42
        ))
    ])
    
    print("Starting training with defined generalization parameters...")
    pipeline.fit(X_train, y_train)
    best_model = pipeline
    
    y_pred = best_model.predict(X_test)
    
    # Baseline comparison (Mean Baseline)
    y_pred_baseline = np.full_like(y_test, global_mean)
    rmse_baseline = np.sqrt(mean_squared_error(y_test, y_pred_baseline))
    mae_baseline = mean_absolute_error(y_test, y_pred_baseline)
    r2_baseline = r2_score(y_test, y_pred_baseline)
    
    mse = mean_squared_error(y_test, y_pred)
    rmse = np.sqrt(mse)
    mae = mean_absolute_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)
    
    actual_bands = get_risk_bands(y_test)
    pred_bands = get_risk_bands(y_pred)
    risk_band_accuracy = float(np.mean(actual_bands == pred_bands))
    
    actual_high_crit = np.isin(actual_bands, ["High", "Critical"])
    pred_high_crit = np.isin(pred_bands, ["High", "Critical"])
    if np.sum(actual_high_crit) > 0:
        high_or_critical_recall = float(np.sum(actual_high_crit & pred_high_crit) / np.sum(actual_high_crit))
    else:
        high_or_critical_recall = 1.0
        
    def get_readable_xgboost_feature_names(preprocessor, original_features, xgb_model):
        try:
            raw_names = preprocessor.get_feature_names_out()
        except Exception:
            raw_names = []
            try:
                for name, trans, columns in preprocessor.transformers_:
                    if name == 'cat' and trans != 'drop':
                        cats = trans.categories_
                        for i, col in enumerate(columns):
                            for cat in cats[i]:
                                raw_names.append(f"{col}_{cat}")
                    elif name == 'cyc' and trans != 'drop':
                        for col in columns:
                            raw_names.append(f"{col}_sin")
                            raw_names.append(f"{col}_cos")
                    elif name == 'num' and trans != 'drop':
                        for col in columns:
                            raw_names.append(col)
                    elif name == 'remainder' and trans == 'passthrough':
                        pass
            except Exception:
                pass

        if not raw_names or len(raw_names) != len(xgb_model.feature_importances_):
            return [f"feature_{i}" for i in range(len(xgb_model.feature_importances_))]

        readable_names = []
        for name in raw_names:
            name = str(name).replace("cat__", "").replace("cyc__", "").replace("num__", "").replace("remainder__", "")
            if name.startswith("hospital_name_"): name = "Hospital: " + name.replace("hospital_name_", "")
            elif name.startswith("region_"): name = "Region: " + name.replace("region_", "")
            elif name.startswith("season_"): name = "Season: " + name.replace("season_", "")
            elif name.startswith("shift_type_"): name = "Shift Type: " + name.replace("shift_type_", "")
            elif name.startswith("x0_"): name = "Hospital: " + name.replace("x0_", "")
            elif name.startswith("x1_"): name = "Region: " + name.replace("x1_", "")
            elif name.startswith("x2_"): name = "Season: " + name.replace("x2_", "")
            elif name.startswith("x3_"): name = "Shift Type: " + name.replace("x3_", "")
            elif name.startswith("size_tier_"): name = "Size Tier: " + name.replace("size_tier_", "")
            elif name.startswith("x4_"): name = "Size Tier: " + name.replace("x4_", "")
            else:
                name = name.replace("_", " ").title()
            readable_names.append(name)
        return readable_names

    transformed_names = get_readable_xgboost_feature_names(preprocessor, features, best_model.named_steps['regressor'])

    
    payload = {
        "model": best_model,
        "features": features,
        "readable_feature_names": transformed_names,
        "metrics": {"mse": mse, "r2": r2},
        "target_encoding": {
            "global_mean": global_mean,
            "hosp_mean": hosp_mean,
            "hosp_hour_mean": {f"{k[0]}|{k[1]}": v for k,v in hosp_hour_mean.items()},
            "reg_mean": reg_mean,
            "reg_hour_mean": {f"{k[0]}|{k[1]}": v for k,v in reg_hour_mean.items()}
        }
    }
    
    with open(model_path, "wb") as f:
        pickle.dump(payload, f)
        
    metrics_path = os.path.join(BASE_DIR, "model_metrics.json")
    
    metrics_data = {
        "metrics": {
            "mae": float(mae),
            "rmse": float(rmse),
            "r2": float(r2),
            "risk_band_accuracy": risk_band_accuracy,
            "high_or_critical_recall": high_or_critical_recall
        },
        "baseline_metrics": {
            "mae": float(mae_baseline),
            "rmse": float(rmse_baseline),
            "r2": float(r2_baseline)
        },
        "training_metadata": {
            "train_rows": len(X_train),
            "test_rows": len(X_test),
            "features_used": features,
            "readable_feature_names": transformed_names,
            "model_path": model_path,
            "last_trained_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "model_purpose": "Early-warning staffing risk detection, not exact clinical wait-time guarantee.",
            "dataset_type": "Synthetic Kaggle ER wait-time dataset",
            "dataset_note": "This project uses the Kaggle ER Wait Time dataset, which is synthetic/simulated emergency department data. It does not contain real patient records or PHI. Real hospital deployment would require retraining and validation on hospital-specific operational data.",
            "skipped_features_note": "The raw dataset does not contain true ESI acuity counts, boarding patient count, lab turnaround time, radiology latency, or live waiting-room census. These were not used as current model inputs to avoid fabricating clinical variables. Rolling and lag features were skipped because the Kaggle dataset does not provide reliable chronological patient-arrival sequencing."
        }
    }
    with open(metrics_path, "w") as f:
        json.dump(metrics_data, f, indent=4)
        
    print(f"Model trained. MSE: {mse:.2f}, R2: {r2:.2f}. Saved model to: {model_path}")
    print(f"Risk Band Accuracy: {risk_band_accuracy:.2f}, High/Critical Recall: {high_or_critical_recall:.2f}")
    return mse, r2

def predict_wait_time(
    facility_size_beds: int,
    month: int,
    day_of_week: int,
    visithour: int,
    urgency_level: int,
    nurse_to_patient_ratio: float,
    specialist_availability: int,
    hospital_name: str = "Riverside Medical Center",
    region: str = "Urban",
    model_path: str = MODEL_PATH
) -> float:
    payload = load_model_payload(model_path)

    model = payload["model"]
    features_list = payload["features"]
    
    input_data = pd.DataFrame([{
        "hospital_name": hospital_name,
        "region": region,
        "facility_size_beds": facility_size_beds,
        "month": month,
        "day_of_week": day_of_week,
        "visithour": visithour,
        "urgency_level": urgency_level,
        "nurse_to_patient_ratio": nurse_to_patient_ratio,
        "specialist_availability": specialist_availability
    }])
    
    input_data = add_derived_features(input_data)
    
    # Re-apply historical features using saved target encoding
    te = payload.get("target_encoding", {})
    global_mean = te.get("global_mean", 45.0)
    hosp_mean = te.get("hosp_mean", {})
    hosp_hour_mean = te.get("hosp_hour_mean", {})
    reg_mean = te.get("reg_mean", {})
    reg_hour_mean = te.get("reg_hour_mean", {})
    
    input_data['hospital_historical_avg_wait'] = input_data['hospital_name'].map(hosp_mean).fillna(global_mean)
    input_data['hospital_hour_historical_avg_wait'] = input_data.apply(lambda row: hosp_hour_mean.get(f"{row['hospital_name']}|{row['visithour']}", global_mean), axis=1)
    input_data['region_historical_avg_wait'] = input_data['region'].map(reg_mean).fillna(global_mean)
    input_data['region_hour_historical_avg_wait'] = input_data.apply(lambda row: reg_hour_mean.get(f"{row['region']}|{row['visithour']}", global_mean), axis=1)
    
    # Ensure all missing features from the list exist
    for feature in features_list:
        if feature not in input_data.columns:
            input_data[feature] = 0
            
    input_data = input_data[features_list]
    prediction = model.predict(input_data)[0]
    return float(np.round(prediction, 1))

if __name__ == "__main__":
    train_model()
