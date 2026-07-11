import os
import pandas as pd
import numpy as np

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KAGGLE_CSV = os.path.join(BASE_DIR, "ER Wait Time Dataset.csv")
OUTPUT_CSV = os.path.join(BASE_DIR, "er_wait_time_real.csv")

def process_data():
    if not os.path.exists(KAGGLE_CSV):
        print(f"File not found: {KAGGLE_CSV}")
        return

    df = pd.read_csv(KAGGLE_CSV)
    
    # 1. facility_size_beds
    df['facility_size_beds'] = df['Facility Size (Beds)']
    
    # 2. month
    visit_dates = pd.to_datetime(df['Visit Date'])
    df['month'] = visit_dates.dt.month
    
    # 3. visithour
    df['visithour'] = visit_dates.dt.hour
    
    # 4. day_of_week
    # Pandas dayofweek: Monday=0, Sunday=6
    df['day_of_week'] = visit_dates.dt.dayofweek
    
    # 5. urgency_level
    # Map to 1 (Low) to 4 (Critical)
    urgency_map = {'Low': 1, 'Medium': 2, 'High': 3, 'Critical': 4}
    df['urgency_level'] = df['Urgency Level'].map(urgency_map)
    
    # 6. nurse_to_patient_ratio
    # Convert integer denominator to ratio (e.g. 4 -> 0.25)
    df['nurse_to_patient_ratio'] = 1.0 / df['Nurse-to-Patient Ratio']
    
    # 7. specialist_availability
    # We will keep the integer count instead of binarizing
    df['specialist_availability'] = df['Specialist Availability']
    
    # 8. wait_time
    df['wait_time'] = df['Total Wait Time (min)']
    
    # 9. patient_satisfaction
    df['patient_satisfaction'] = df['Patient Satisfaction']
    
    # 10. hospital_name
    df['hospital_name'] = df['Hospital Name']
    
    # 11. region
    df['region'] = df['Region']
    
    # Select columns to match the synthetic data format
    final_cols = [
        'hospital_name',
        'region',
        'facility_size_beds',
        'month',
        'day_of_week',
        'visithour',
        'urgency_level',
        'nurse_to_patient_ratio',
        'specialist_availability',
        'wait_time',
        'patient_satisfaction'
    ]
    
    processed_df = df[final_cols]
    
    # Save and overwrite the synthetic dataset
    processed_df.to_csv(OUTPUT_CSV, index=False)
    print(f"Processed {len(processed_df)} rows and saved to {OUTPUT_CSV}")

if __name__ == "__main__":
    process_data()
