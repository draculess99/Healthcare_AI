import xgboost as xgb
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
import pandas as pd
import numpy as np
import os
import json
import pickle
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from sklearn.preprocessing import StandardScaler

import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
try:
    from backend.data_loader import get_heart_disease_data
except ImportError:
    from data_loader import get_heart_disease_data

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
METRICS_PATH = os.path.join(DATA_DIR, 'metrics.json')
DATASET_FILE = os.path.join(DATA_DIR, 'current_dataset.txt')

MODEL_PATHS = {
    'XGBoost': os.path.join(DATA_DIR, 'xgboost_model.json'),
    'Random Forest': os.path.join(DATA_DIR, 'rf_model.pkl'),
    'Logistic Regression': os.path.join(DATA_DIR, 'lr_model.pkl')
}
SCALER_PATH = os.path.join(DATA_DIR, 'scaler.pkl')

def train_models(dataset_name="UCI Cleveland Original"):
    """Trains multiple classification models on real UCI data."""
    X, y = get_heart_disease_data(dataset_name)
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # Scale data for Logistic Regression
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    with open(SCALER_PATH, 'wb') as f:
        pickle.dump(scaler, f)
    
    models = {
        'XGBoost': xgb.XGBClassifier(use_label_encoder=False, eval_metric='logloss', n_estimators=100, random_state=42),
        'Random Forest': RandomForestClassifier(n_estimators=100, random_state=42),
        'Logistic Regression': LogisticRegression(max_iter=1000, random_state=42)
    }
    
    all_metrics = {}
    
    for name, model in models.items():
        if name == 'Logistic Regression':
            model.fit(X_train_scaled, y_train)
            y_pred = model.predict(X_test_scaled)
        else:
            model.fit(X_train, y_train)
            y_pred = model.predict(X_test)
            
        # Save models
        if name == 'XGBoost':
            model.save_model(MODEL_PATHS[name])
        else:
            with open(MODEL_PATHS[name], 'wb') as f:
                pickle.dump(model, f)
                
        # Calculate metrics
        all_metrics[name] = {
            "Accuracy": float(accuracy_score(y_test, y_pred)),
            "Precision": float(precision_score(y_test, y_pred)),
            "Recall": float(recall_score(y_test, y_pred)),
            "F1 Score": float(f1_score(y_test, y_pred))
        }
    
    with open(METRICS_PATH, 'w') as f:
        json.dump(all_metrics, f, indent=4)
        
    with open(DATASET_FILE, 'w') as f:
        f.write(dataset_name)
        
    print(f"All models trained on {dataset_name} and metrics saved.")

def get_disease_probability(age, sex, cp, trestbps, chol, fbs, thalach, model_name='XGBoost', dataset_name="UCI Cleveland Original"):
    """Returns probability of heart disease (0.0 to 1.0) using the selected model."""
    current_dataset = None
    if os.path.exists(DATASET_FILE):
        with open(DATASET_FILE, 'r') as f:
            current_dataset = f.read().strip()
            
    if not os.path.exists(MODEL_PATHS['XGBoost']) or current_dataset != dataset_name:
        train_models(dataset_name)
        
    X = pd.DataFrame({
        'age': [age], 'sex': [sex], 'cp': [cp], 'trestbps': [trestbps], 
        'chol': [chol], 'fbs': [fbs], 'thalach': [thalach]
    })
    
    if model_name == 'Logistic Regression':
        with open(SCALER_PATH, 'rb') as f:
            scaler = pickle.load(f)
        X_input = scaler.transform(X)
    else:
        X_input = X
        
    if model_name == 'XGBoost':
        model = xgb.XGBClassifier()
        model.load_model(MODEL_PATHS['XGBoost'])
    else:
        with open(MODEL_PATHS[model_name], 'rb') as f:
            model = pickle.load(f)
            
    probability = model.predict_proba(X_input)[0][1]
    return float(probability)

def get_xai_data(model_name='XGBoost', dataset_name="UCI Cleveland Original"):
    """Extracts feature importances, correlations, and means for XAI."""
    import pandas as pd
    
    current_dataset = None
    if os.path.exists(DATASET_FILE):
        with open(DATASET_FILE, 'r') as f:
            current_dataset = f.read().strip()
            
    if not os.path.exists(MODEL_PATHS['XGBoost']) or current_dataset != dataset_name:
        train_models(dataset_name)
        
    X, y = get_heart_disease_data(dataset_name)
    df = X.copy()
    df['target'] = y
    
    # Correlation Matrix
    corr_matrix = df.corr().to_dict()
    
    # Means
    means_disease = df[df['target'] == 1].drop(columns=['target']).mean().to_dict()
    means_healthy = df[df['target'] == 0].drop(columns=['target']).mean().to_dict()
    
    # Feature Importance
    importances = {}
    features = X.columns.tolist()
    
    try:
        if model_name == 'XGBoost':
            model = xgb.XGBClassifier()
            model.load_model(MODEL_PATHS['XGBoost'])
            imp_vals = model.feature_importances_
        else:
            with open(MODEL_PATHS[model_name], 'rb') as f:
                model = pickle.load(f)
            if model_name == 'Random Forest':
                imp_vals = model.feature_importances_
            elif model_name == 'Logistic Regression':
                imp_vals = np.abs(model.coef_[0])
        
        # Normalize importances
        total = sum(imp_vals)
        importances = {feat: float(val/total) for feat, val in zip(features, imp_vals)}
    except Exception as e:
        print(f"Error getting feature importances: {e}")
        
    return {
        "correlations": corr_matrix,
        "means_disease": means_disease,
        "means_healthy": means_healthy,
        "importances": importances
    }

if __name__ == "__main__":
    train_models()
