import pandas as pd
import numpy as np
import os
import random

def generate_dataset(num_patients=500, output_path="database/bedflow_patient_data.csv"):
    np.random.seed(42)
    random.seed(42)

    data = []
    for i in range(num_patients):
        patient_id = f"PT{i:04d}"
        age = np.random.randint(18, 95)
        diagnosis_groups = ["Cardiology", "Neurology", "Orthopedics", "General Medicine", "Oncology", "Pulmonology"]
        diagnosis_group = np.random.choice(diagnosis_groups)
        acuity_level = np.random.choice(["Low", "Medium", "High"], p=[0.5, 0.3, 0.2])
        length_of_stay_days = np.random.randint(1, 30)
        
        prior_admissions_6mo = np.random.randint(0, 5)
        prior_ed_visits_6mo = np.random.randint(0, 8)
        prior_readmissions_12mo = np.random.randint(0, 4)
        
        medication_count = np.random.randint(1, 20)
        medication_complexity = np.random.choice(["Low", "Medium", "High"], p=[0.4, 0.4, 0.2])
        
        mobility_status = np.random.choice(["Independent", "Assisted", "Bedbound"])
        home_support_level = np.random.choice(["Good", "Fair", "Poor", "None"])
        lives_alone = np.random.choice([0, 1])
        
        destinations = ["Home", "SNF", "Rehab", "LTC", "Hospice"]
        discharge_destination = np.random.choice(destinations, p=[0.6, 0.15, 0.15, 0.05, 0.05])
        
        doctor_signoff_pending = np.random.choice([0, 1], p=[0.8, 0.2])
        pharmacy_med_rec_pending = np.random.choice([0, 1], p=[0.7, 0.3])
        transport_pending = np.random.choice([0, 1], p=[0.7, 0.3])
        insurance_authorization_pending = np.random.choice([0, 1], p=[0.8, 0.2])
        rehab_snf_placement_pending = np.random.choice([0, 1], p=[0.9, 0.1])
        if discharge_destination in ["SNF", "Rehab"]:
            rehab_snf_placement_pending = np.random.choice([0, 1], p=[0.4, 0.6])
            
        home_care_setup_pending = np.random.choice([0, 1], p=[0.8, 0.2])
        social_work_pending = np.random.choice([0, 1], p=[0.75, 0.25])
        family_pickup_pending = np.random.choice([0, 1], p=[0.8, 0.2])
        
        lab_stability_flag = np.random.choice(["Stable", "Unstable", "Pending"], p=[0.8, 0.1, 0.1])
        vital_sign_stability_flag = np.random.choice(["Stable", "Unstable"], p=[0.9, 0.1])
        
        current_bed_occupancy_percent = np.random.randint(70, 100)
        ed_boarding_count = np.random.randint(0, 30)
        ed_wait_time_pressure = np.random.choice(["Low", "Medium", "High", "Critical"])
        
        weekend_discharge_flag = np.random.choice([0, 1], p=[0.7, 0.3])
        after_hours_flag = np.random.choice([0, 1], p=[0.8, 0.2])
        case_manager_available = np.random.choice([0, 1], p=[0.1, 0.9])

        # Logic for targets
        delay_score = (
            doctor_signoff_pending * 3 +
            pharmacy_med_rec_pending * 2 +
            transport_pending * 2 +
            insurance_authorization_pending * 5 +
            rehab_snf_placement_pending * 6 +
            home_care_setup_pending * 4 +
            social_work_pending * 3 +
            family_pickup_pending * 2 +
            (1 if lab_stability_flag != "Stable" else 0) * 3 +
            (1 if vital_sign_stability_flag == "Unstable" else 0) * 4
        )
        
        delayed_discharge = 1 if delay_score > 5 else 0
        expected_discharge_delay_hours = min(48, max(0, delay_score * 1.5 + np.random.normal(0, 2)))
        if delay_score == 0:
            expected_discharge_delay_hours = 0
            
        readmission_score = (
            prior_admissions_6mo * 2 +
            prior_readmissions_12mo * 3 +
            (1 if medication_complexity == "High" else 0) * 2 +
            (1 if home_support_level in ["Poor", "None"] else 0) * 2 +
            (1 if mobility_status != "Independent" else 0) * 1 +
            (1 if acuity_level == "High" else 0) * 2
        )
        readmitted_30_days = 1 if readmission_score > 6 else 0
        
        primary_discharge_bottleneck = "None"
        if delayed_discharge:
            bottlenecks = []
            if rehab_snf_placement_pending: bottlenecks.append("Rehab/SNF")
            if insurance_authorization_pending: bottlenecks.append("Insurance")
            if home_care_setup_pending: bottlenecks.append("Home Care")
            if pharmacy_med_rec_pending: bottlenecks.append("Pharmacy")
            if transport_pending: bottlenecks.append("Transport")
            if doctor_signoff_pending: bottlenecks.append("Doctor")
            if lab_stability_flag != "Stable" or vital_sign_stability_flag == "Unstable":
                bottlenecks.append("Clinical Stability")
            
            if bottlenecks:
                primary_discharge_bottleneck = bottlenecks[0] # Pick the first major one
            else:
                primary_discharge_bottleneck = "Other"

        data.append({
            "patient_id": patient_id,
            "age": age,
            "diagnosis_group": diagnosis_group,
            "acuity_level": acuity_level,
            "length_of_stay_days": length_of_stay_days,
            "prior_admissions_6mo": prior_admissions_6mo,
            "prior_ed_visits_6mo": prior_ed_visits_6mo,
            "prior_readmissions_12mo": prior_readmissions_12mo,
            "medication_count": medication_count,
            "medication_complexity": medication_complexity,
            "mobility_status": mobility_status,
            "home_support_level": home_support_level,
            "lives_alone": lives_alone,
            "discharge_destination": discharge_destination,
            "doctor_signoff_pending": doctor_signoff_pending,
            "pharmacy_med_rec_pending": pharmacy_med_rec_pending,
            "transport_pending": transport_pending,
            "insurance_authorization_pending": insurance_authorization_pending,
            "rehab_snf_placement_pending": rehab_snf_placement_pending,
            "home_care_setup_pending": home_care_setup_pending,
            "social_work_pending": social_work_pending,
            "family_pickup_pending": family_pickup_pending,
            "lab_stability_flag": lab_stability_flag,
            "vital_sign_stability_flag": vital_sign_stability_flag,
            "current_bed_occupancy_percent": current_bed_occupancy_percent,
            "ed_boarding_count": ed_boarding_count,
            "ed_wait_time_pressure": ed_wait_time_pressure,
            "weekend_discharge_flag": weekend_discharge_flag,
            "after_hours_flag": after_hours_flag,
            "case_manager_available": case_manager_available,
            "delayed_discharge": delayed_discharge,
            "readmitted_30_days": readmitted_30_days,
            "expected_discharge_delay_hours": round(expected_discharge_delay_hours, 1),
            "primary_discharge_bottleneck": primary_discharge_bottleneck
        })

    df = pd.DataFrame(data)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"Generated {num_patients} synthetic patient records at {output_path}")

if __name__ == "__main__":
    generate_dataset()
