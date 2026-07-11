import pandas as pd
import requests
import io
import numpy as np

DATA_URL = "https://archive.ics.uci.edu/ml/machine-learning-databases/heart-disease/processed.cleveland.data"

def get_heart_disease_data(dataset_name="UCI Cleveland Original"):
    """Downloads and cleans the UCI Heart Disease dataset or generates synthetic data."""
    if dataset_name == "Synthetic Global Cohort (10,000 Patients)":
        print("Generating 10,000 synthetic patient records...")
        np.random.seed(42)
        n = 10000
        age = np.random.normal(54, 9, n).clip(20, 90).astype(int)
        sex = np.random.binomial(1, 0.68, n)
        cp = np.random.choice([1, 2, 3, 4], n, p=[0.08, 0.16, 0.28, 0.48])
        trestbps = np.random.normal(131, 17, n).clip(90, 200).astype(int)
        chol = np.random.normal(246, 51, n).clip(120, 500).astype(int)
        fbs = np.random.binomial(1, 0.15, n)
        thalach = np.random.normal(149, 23, n).clip(70, 210).astype(int)
        
        # Determine target based on simple realistic rules to make the models learn something
        risk_score = (age / 100.0) + (trestbps / 200.0) + (chol / 400.0) - (thalach / 250.0) + (cp / 4.0)
        prob = 1 / (1 + np.exp(-(risk_score - 1.5) * 5))
        target = np.random.binomial(1, prob, n)
        
        X = pd.DataFrame({
            'age': age, 'sex': sex, 'cp': cp, 'trestbps': trestbps,
            'chol': chol, 'fbs': fbs, 'thalach': thalach
        })
        y = pd.Series(target)
        return X, y
        
    elif dataset_name == "High-Risk Elderly Cohort (2,000 Patients)":
        print("Generating 2,000 high-risk elderly patient records...")
        np.random.seed(101)
        n = 2000
        age = np.random.normal(75, 5, n).clip(60, 95).astype(int)
        sex = np.random.binomial(1, 0.5, n)
        cp = np.random.choice([1, 2, 3, 4], n, p=[0.2, 0.2, 0.3, 0.3])
        trestbps = np.random.normal(150, 20, n).clip(110, 220).astype(int)
        chol = np.random.normal(280, 40, n).clip(180, 400).astype(int)
        fbs = np.random.binomial(1, 0.3, n)
        thalach = np.random.normal(120, 15, n).clip(60, 160).astype(int)
        
        risk_score = (age / 100.0) + (trestbps / 200.0) + (chol / 400.0) - (thalach / 250.0) + (cp / 4.0)
        prob = 1 / (1 + np.exp(-(risk_score - 1.2) * 5))
        target = np.random.binomial(1, prob, n)
        
        X = pd.DataFrame({'age': age, 'sex': sex, 'cp': cp, 'trestbps': trestbps, 'chol': chol, 'fbs': fbs, 'thalach': thalach})
        y = pd.Series(target)
        return X, y
        
    elif dataset_name == "Global General Population (50,000 Patients)":
        print("Generating 50,000 general population patient records...")
        np.random.seed(202)
        n = 50000
        age = np.random.normal(45, 12, n).clip(18, 85).astype(int)
        sex = np.random.binomial(1, 0.5, n)
        cp = np.random.choice([1, 2, 3, 4], n, p=[0.05, 0.1, 0.15, 0.7])
        trestbps = np.random.normal(120, 15, n).clip(90, 180).astype(int)
        chol = np.random.normal(200, 35, n).clip(100, 350).astype(int)
        fbs = np.random.binomial(1, 0.05, n)
        thalach = np.random.normal(160, 20, n).clip(80, 220).astype(int)
        
        risk_score = (age / 100.0) + (trestbps / 200.0) + (chol / 400.0) - (thalach / 250.0) + (cp / 4.0)
        prob = 1 / (1 + np.exp(-(risk_score - 1.8) * 5))
        target = np.random.binomial(1, prob, n)
        
        X = pd.DataFrame({'age': age, 'sex': sex, 'cp': cp, 'trestbps': trestbps, 'chol': chol, 'fbs': fbs, 'thalach': thalach})
        y = pd.Series(target)
        return X, y

    columns = [
        'age', 'sex', 'cp', 'trestbps', 'chol', 'fbs', 'restecg', 
        'thalach', 'exang', 'oldpeak', 'slope', 'ca', 'thal', 'target'
    ]
    
    print("Downloading UCI Heart Disease dataset...")
    response = requests.get(DATA_URL)
    response.raise_for_status()
    
    # Read CSV
    df = pd.read_csv(io.StringIO(response.text), names=columns, na_values="?")
    
    # Drop rows with missing values
    df.dropna(inplace=True)
    
    # Select our subset of features for the UI
    features_to_use = ['age', 'sex', 'cp', 'trestbps', 'chol', 'fbs', 'thalach']
    
    X = df[features_to_use]
    
    # Convert target to binary (0 = no disease, 1 = disease present)
    y = (df['target'] > 0).astype(int)
    
    return X, y
