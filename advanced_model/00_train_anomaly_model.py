# 00_train_anomaly_model.py (Corrected Column Names)

import pandas as pd
from sklearn.ensemble import IsolationForest
import joblib
import os

print("Starting Anomaly Detection Model Training...")

# --- Configuration ---
DATA_DIR = "source_data"
MODEL_OUTPUT_FILE = "anomaly_model.joblib"
DATASET_FILE = "dataset_train.csv"

# --- Main Training Logic ---
def train_anomaly_model():
    """
    Loads the MetroPT dataset, trains an Isolation Forest model, and saves it.
    """
    try:
        df = pd.read_csv(os.path.join(DATA_DIR, DATASET_FILE))
        print(f"  Dataset with {len(df)} rows loaded successfully.")
    except FileNotFoundError:
        print(f"Error: Dataset '{DATASET_FILE}' not found in '{DATA_DIR}' directory.")
        return

    # +++ MODIFIED PART: Using your exact column names +++
    features = [
        'TP2', 'TP3', 'H1', 'DV_pressure', 'Reservoirs', 'Oil_temperature', 
        'Motor_current', 'COMP', 'DV_eletric', 'Towers', 'MPG', 'LPS', 
        'Pressure_switch', 'Oil_level', 'Caudal_impulses', 'gpsSpeed' # Corrected 'Caudal_impulses'
    ]
    
    column_mapping = {
        'DV_pressu': 'DV_pressure',
        'Oil_temper': 'Oil_temperature',
        'Motor_curr': 'Motor_current',
    }
    df.rename(columns=column_mapping, inplace=True)
    
    target = 'failure'

    required_cols = features
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        print(f"Error: The following required columns are missing from the CSV file: {missing_cols}")
        return

    df.dropna(subset=features, inplace=True)
    X = df[features]
    
    print(f"  Training Isolation Forest on {len(X)} data points...")
    model = IsolationForest(n_estimators=100, contamination='auto', random_state=42, n_jobs=-1)
    model.fit(X)

    print(f"  Saving trained model to '{MODEL_OUTPUT_FILE}'...")
    joblib.dump(model, MODEL_OUTPUT_FILE)
    print("\nAnomaly detection model training complete.")

if __name__ == "__main__":
    train_anomaly_model()