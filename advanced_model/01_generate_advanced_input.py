# 01_generate_advanced_input.py (Refactored with Shunting Data)

import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta
import random
import joblib
import os

print("Starting Advanced Input Data Generation...")

# --- Configuration ---
NUM_TRAINS = 25
PLANNING_DATE = datetime.now()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(BASE_DIR, "daily_input")
SOURCE_DATA_DIR = os.path.join(BASE_DIR, "source_data")

# --- 1. Process GTFS Data ---
def process_gtfs_data(gtfs_path, planning_date):
    """
    Loads GTFS data, calculates trip details, and determines next-day start requirements.
    """
    print("  Processing GTFS data...")
    try:
        trips_df = pd.read_csv(os.path.join(gtfs_path, 'trips.txt'))
        shapes_df = pd.read_csv(os.path.join(gtfs_path, 'shapes.txt'))
        stop_times_df = pd.read_csv(os.path.join(gtfs_path, 'stop_times.txt'))
        
        # --- Process all trips first ---
        shape_distances = shapes_df.groupby('shape_id')['shape_dist_traveled'].max().reset_index()
        shape_distances = shape_distances.rename(columns={'shape_dist_traveled': 'distance_km'})

        stop_times_df['departure_time_td'] = pd.to_timedelta(stop_times_df['departure_time'])
        stop_times_df['arrival_time_td'] = pd.to_timedelta(stop_times_df['arrival_time'])
        
        start_stops = stop_times_df.loc[stop_times_df.groupby('trip_id')['stop_sequence'].idxmin()]
        end_stops = stop_times_df.loc[stop_times_df.groupby('trip_id')['stop_sequence'].idxmax()]
        
        trip_terminals = pd.merge(
            start_stops[['trip_id', 'stop_id']], end_stops[['trip_id', 'stop_id']],
            on='trip_id', suffixes=('_start', '_end')
        )
        
        trip_times = stop_times_df.groupby('trip_id').agg(
            start_time=('departure_time_td', 'min'),
            end_time=('arrival_time_td', 'max')
        ).reset_index()
        trip_times['duration_hours'] = (trip_times['end_time'] - trip_times['start_time']).dt.total_seconds() / 3600
        
        all_trip_details = pd.merge(trips_df, shape_distances, on='shape_id', how='left')
        all_trip_details = pd.merge(all_trip_details, trip_times, on='trip_id', how='left')
        all_trip_details = pd.merge(all_trip_details, trip_terminals, on='trip_id', how='left')
        all_trip_details.dropna(subset=['distance_km', 'duration_hours'], inplace=True)

        # --- Get details for the PLANNING_DATE ---
        service_id_today = 'WK' if planning_date.weekday() < 6 else 'WE'
        today_trips = all_trip_details[all_trip_details['service_id'] == service_id_today].copy()
        
        # Identify late evening trips for shunting calculation
        LATE_EVENING_START_TIME = timedelta(hours=22)
        today_trips['is_late_evening'] = today_trips['end_time'] > LATE_EVENING_START_TIME
        
        # --- Get details for the NEXT DAY'S morning departures ---
        next_day = planning_date + timedelta(days=1)
        service_id_next_day = 'WK' if next_day.weekday() < 6 else 'WE'
        next_day_trips = all_trip_details[all_trip_details['service_id'] == service_id_next_day].copy()
        
        MORNING_RUSH_END_TIME = timedelta(hours=7)
        next_morning_trips = next_day_trips[next_day_trips['start_time'] < MORNING_RUSH_END_TIME]
        
        next_day_starts = next_morning_trips.groupby('stop_id_start').size().to_dict()
        
        # Convert timedeltas to strings for JSON
        today_trips['start_time'] = today_trips['start_time'].astype(str).str.split(' ').str[-1]
        today_trips['end_time'] = today_trips['end_time'].astype(str).str.split(' ').str[-1]

        print(f"    -> Processed {len(today_trips)} trips for {planning_date.date()} (Service ID: {service_id_today})")
        print(f"    -> Next morning requires starts: {next_day_starts}")
        
        return today_trips, next_day_starts

    except FileNotFoundError as e:
        print(f"Error: {e}. Make sure GTFS files are in '{gtfs_path}'")
        return None, None

# --- 2. Generate Synthetic Fleet Data ---
def generate_synthetic_data(num_trains, planning_date):
    print("  Generating synthetic fleet data...")
    try:
        anomaly_model = joblib.load("anomaly_model.joblib")
        print("    -> Anomaly detection model loaded.")
    except FileNotFoundError:
        print("Error: Model file 'anomaly_model.joblib' not found. Please run '00_train_anomaly_model.py' first.")
        return None, None, None, None

    train_ids = [f"T{str(i).zfill(2)}" for i in range(1, num_trains + 1)]
    fleet_df = pd.DataFrame({'train_id': train_ids})
    fleet_df['initial_mileage_km'] = np.random.normal(loc=80000, scale=20000, size=num_trains).astype(int)
    
    # +++ MODIFIED PART: Using your exact column names for simulation +++
    health_scores = []
    sensor_features = [
        'TP2', 'TP3', 'H1', 'DV_pressure', 'Reservoirs', 'Oil_temperature', 
        'Motor_current', 'COMP', 'DV_eletric', 'Towers', 'MPG', 'LPS', 
        'Pressure_switch', 'Oil_level', 'Caudal_impulses', 'gpsSpeed' # Corrected 'Caudal_impulses'
    ]
    
    for train_id in train_ids:
        if random.random() < 0.2:
            simulated_sensors = [np.random.uniform(low=100, high=200) for _ in sensor_features]
        else:
            simulated_sensors = [np.random.uniform(low=10, high=50) for _ in sensor_features]
        
        sensor_df = pd.DataFrame([simulated_sensors], columns=sensor_features)
        
        anomaly_score = anomaly_model.decision_function(sensor_df)[0]
        risk_score = 1 / (1 + np.exp(anomaly_score))
        health_scores.append(round(risk_score, 4))
        
    fleet_df['health_score'] = health_scores
    print("    -> Generated predictive health scores for all trains.")

    # ... (The rest of the function remains the same) ...
    fleet_df['last_deep_clean_date'] = [planning_date.date() - timedelta(days=random.randint(1, 10)) for _ in range(num_trains)]
    fleet_df['telecom_cert_expiry_date'] = [planning_date.date() + timedelta(days=random.randint(-2, 30)) for _ in range(num_trains)]
    fleet_df['stock_cert_expiry_date'] = [planning_date.date() + timedelta(days=random.randint(5, 60)) for _ in range(num_trains)]
    fleet_df['signal_cert_expiry_km'] = fleet_df['initial_mileage_km'] + np.random.randint(1000, 5000, size=num_trains)

    for col in ['last_deep_clean_date', 'telecom_cert_expiry_date', 'stock_cert_expiry_date']:
        fleet_df[col] = fleet_df[col].astype(str)

    job_cards_df = pd.DataFrame({'train_id': random.sample(train_ids, k=3), 'status': 'OPEN'})
    ad_contracts_df = pd.DataFrame({'train_id': random.sample(train_ids, k=5), 'contract_total_hours': np.random.randint(100, 200, size=5).tolist(), 'hours_completed': np.random.randint(20, 100, size=5).tolist()})
    depot_resources = {"cleaning_bays": 4, "deep_clean_threshold_days": 7}

    return fleet_df, job_cards_df, ad_contracts_df, depot_resources

# --- Main Execution ---
if __name__ == "__main__":
    os.makedirs(INPUT_DIR, exist_ok=True)

    trip_details_df, next_day_starts = process_gtfs_data(SOURCE_DATA_DIR, PLANNING_DATE)
    
    if trip_details_df is not None:
        fleet_df, job_cards_df, ad_contracts_df, depot_resources = generate_synthetic_data(NUM_TRAINS, PLANNING_DATE)
        
        daily_input_data = {
            "planning_date": PLANNING_DATE.strftime('%Y-%m-%d'),
            "fleet_details": fleet_df.to_dict(orient='records'),
            "job_cards": job_cards_df.to_dict(orient='records'),
            "ad_contracts": ad_contracts_df.to_dict(orient='records'),
            "depot_resources": depot_resources,
            "trip_details": trip_details_df.to_dict(orient='records'),
            "next_day_starts": next_day_starts  # NEW: Add next day's data
        }
        
        file_date = PLANNING_DATE.strftime('%Y-%m-%d')
        output_filename = os.path.join(INPUT_DIR, f"{file_date}_input_data.json")
        
        with open(output_filename, 'w') as f:
            json.dump(daily_input_data, f, indent=4)
            
        print(f"\nData generation complete. Consolidated input file saved to:\n{output_filename}")