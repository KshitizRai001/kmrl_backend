import pandas as pd
from datetime import datetime, date
import json
import os
import joblib
import numpy as np

def generate_advanced_input(planning_date_str):
    """
    Generates a comprehensive JSON input file for the advanced scheduling solver.
    This version calculates a normalized anomaly_score (where high is bad).
    """
    try:
        print("Loading source data...")
        base_path = 'source_data'
        
        # --- Load all source files and clean column names ---
        fleet_df = pd.read_csv(os.path.join(base_path, 'fleet_details.csv'))
        fleet_df.columns = fleet_df.columns.str.strip()

        job_cards_df = pd.read_csv(os.path.join(base_path, 'job_cards.csv'))
        job_cards_df.columns = job_cards_df.columns.str.strip()

        trips_df = pd.read_csv(os.path.join(base_path, 'trips.txt'))
        trips_df.columns = trips_df.columns.str.strip()

        stop_times_df = pd.read_csv(os.path.join(base_path, 'stop_times.txt'))
        stop_times_df.columns = stop_times_df.columns.str.strip()

        trip_details_df = pd.read_csv(os.path.join(base_path, 'trip_details.csv'))
        trip_details_df.columns = trip_details_df.columns.str.strip()

        certificates_df = pd.read_csv(os.path.join(base_path, 'certificates.csv'))
        certificates_df.columns = certificates_df.columns.str.strip()

        shunting_distances_df = pd.read_csv(os.path.join(base_path, 'shunting_costs.csv'))
        shunting_distances_df.columns = shunting_distances_df.columns.str.strip()

        ad_contracts_df = pd.read_csv(os.path.join(base_path, 'ad_contracts.csv'))
        ad_contracts_df.columns = ad_contracts_df.columns.str.strip()
        
        cleaning_req_df = pd.read_csv(os.path.join(base_path, 'cleaning_requirements.csv'))
        cleaning_req_df.columns = cleaning_req_df.columns.str.strip()
        
        sensor_data_df = pd.read_csv(os.path.join(base_path, 'real_time_sensor_data.csv'))
        sensor_data_df.columns = sensor_data_df.columns.str.strip()
        
        anomaly_model = joblib.load('anomaly_model.joblib')

        with open(os.path.join(base_path, 'depot_resources.json'), 'r') as f:
            depot_resources = json.load(f)

        print("All data files loaded successfully.")
        
        # --- Data Processing ---
        planning_date = datetime.strptime(planning_date_str, '%Y-%m-%d').date()
        
        open_job_cards = set(job_cards_df[job_cards_df['status'] == 'Open']['train_id'])
        active_contracts = ad_contracts_df[ad_contracts_df['hours_completed'] < ad_contracts_df['contract_total_hours']]
        branded_trains = set(active_contracts['train_id'])
        average_fleet_mileage = fleet_df['initial_mileage_km'].mean()
        trains_needing_cleaning = {row['train_id']: row['duration_hours'] for _, row in cleaning_req_df.iterrows()}

        print("Calculating real-time Anomaly Scores...")
        
        features_in_order = anomaly_model.feature_names_in_
        sensor_data_features = sensor_data_df[features_in_order]
        
        anomaly_scores_raw = anomaly_model.decision_function(sensor_data_features)
        
        min_score, max_score = np.min(anomaly_scores_raw), np.max(anomaly_scores_raw)
        if (max_score - min_score) == 0:
            normalized_scores = np.zeros_like(anomaly_scores_raw)
        else:
            # Lower raw score is more anomalous. This normalization makes the most anomalous train's score -> 0
            # and the least anomalous -> 1. This is a "raw health score".
            normalized_scores = (anomaly_scores_raw - min_score) / (max_score - min_score)

        # --- DEFINITIVE FIX: Create a final anomaly_score where HIGH is BAD ---
        # A high anomaly score (near 1.0) means the train is very unhealthy.
        final_anomaly_scores = 1 - normalized_scores

        sensor_data_df['anomaly_score'] = final_anomaly_scores
        train_anomaly_map = sensor_data_df.set_index('train_id')['anomaly_score'].to_dict()

        print("Processing train fleet data...")
        trains_data = []
        for _, train_row in fleet_df.iterrows():
            train_id = train_row['train_id']
            
            certs = certificates_df[certificates_df['train_id'] == train_id]
            is_certified = True
            if not certs.empty:
                for _, cert_row in certs.iterrows():
                    expiry_date = datetime.strptime(cert_row['expiry_date'], '%Y-%m-%d').date()
                    if expiry_date < planning_date:
                        is_certified = False
                        break
            
            anomaly_score_value = round(train_anomaly_map.get(train_id, 0.5), 2)

            trains_data.append({
                'train_id': train_id,
                'mileage': train_row['initial_mileage_km'],
                'has_open_job_card': train_id in open_job_cards,
                'is_fully_certified': is_certified,
                'anomaly_score': anomaly_score_value,
                'has_branding_contract': train_id in branded_trains,
                'cleaning_required_hours': trains_needing_cleaning.get(train_id, 0)
            })

        print("Processing trips data...")
        trip_start_times = stop_times_df.groupby('trip_id')['departure_time'].min().reset_index()
        trip_end_times = stop_times_df.groupby('trip_id')['arrival_time'].max().reset_index()
        trip_start_locations = stop_times_df.loc[stop_times_df.groupby('trip_id')['stop_sequence'].idxmin()]
        trip_end_locations = stop_times_df.loc[stop_times_df.groupby('trip_id')['stop_sequence'].idxmax()]

        merged_trips = pd.merge(trips_df, trip_start_times, on='trip_id')
        merged_trips = pd.merge(merged_trips, trip_end_times, on='trip_id')
        merged_trips = pd.merge(merged_trips, trip_start_locations[['trip_id', 'stop_id']], on='trip_id', suffixes=('', '_start'))
        merged_trips = pd.merge(merged_trips, trip_end_locations[['trip_id', 'stop_id']], on='trip_id', suffixes=('', '_end'))
        merged_trips = pd.merge(merged_trips, trip_details_df[['trip_id', 'distance_km']], on='trip_id')

        trips_data = [ { 'trip_id': row['trip_id'], 'start_time': row['departure_time'], 'end_time': row['arrival_time'], 'start_stop_id': row['stop_id'], 'end_stop_id': row['stop_id_end'], 'distance_km': row['distance_km'] } for _, row in merged_trips.iterrows() ]

        output_data = {
            'planning_date': planning_date_str,
            'trains': trains_data,
            'trips': trips_data,
            'shunting_distances': shunting_distances_df.to_dict(orient='records'),
            'average_fleet_mileage': average_fleet_mileage,
            'depot_resources': depot_resources
        }

        output_dir = 'daily_input'
        os.makedirs(output_dir, exist_ok=True)
        output_filename = os.path.join(output_dir, f"{planning_date_str}_input_data.json")
        with open(output_filename, 'w') as f:
            json.dump(output_data, f, indent=4)
        
        print(f"Input data successfully generated at {output_filename}")

    except FileNotFoundError as e:
        print(f"Error loading data files: {e}. Please ensure all source files are present.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == '__main__':
    planning_date = date.today()
    planning_date_str = planning_date.strftime('%Y-%m-%d')
    print(f"Planning for date: {planning_date_str}")
    generate_advanced_input(planning_date_str)

