# 02_solve_advanced_schedule.py (Final Version with All Fixes)

import pandas as pd
import json
from ortools.sat.python import cp_model
from datetime import datetime, timedelta
import os
import sys

print("Starting Advanced Schedule Solver...")

# --- Configuration ---
try:
    date_str = sys.argv[1]
    PLANNING_DATE = datetime.strptime(date_str, '%Y-%m-%d')
except IndexError:
    PLANNING_DATE = datetime.now()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(BASE_DIR, "daily_input")
SOLUTION_DIR = os.path.join(BASE_DIR, "daily_solution")

# --- Objective Function Weights ---
W_TRIP_COVERAGE = -10000
W_ACTIVATION = 100
W_MILEAGE_RANGE = 1
W_BRANDING = -20
W_CLEANING_PENALTY = 500
W_SHUNTING = 300
W_HEALTH_RISK = 5000  # <--- FIX IS HERE

# --- 1. Load All Input Data ---
def load_input_data(input_file_path):
    print(f"  Loading input data from {input_file_path}...")
    try:
        with open(input_file_path, 'r') as f: data = json.load(f)
        trips = pd.DataFrame(data['trip_details'])
        fleet = pd.DataFrame(data['fleet_details'])
        job_cards = pd.DataFrame(data['job_cards'])
        ad_contracts = pd.DataFrame(data['ad_contracts'])
        depot = data['depot_resources']
        next_day_starts = data['next_day_starts']
        for col in ['last_deep_clean_date', 'telecom_cert_expiry_date', 'stock_cert_expiry_date']: fleet[col] = pd.to_datetime(fleet[col])
        print(f"    -> Loaded {len(trips)} trips, {len(fleet)} trains, and other constraints.")
        return trips, fleet, job_cards, ad_contracts, depot, next_day_starts
    except FileNotFoundError:
        print(f"Error: Input file not found at {input_file_path}")
        return None, None, None, None, None, None

# --- 2. Solve The Schedule ---
def solve_schedule(trips, fleet, job_cards, ad_contracts, depot, next_day_starts):
    model = cp_model.CpModel()
    trains_list = fleet['train_id'].tolist()
    trips_list = trips['trip_id'].tolist()
    
    print("  A. Creating decision variables...")
    assign = { (t, j): model.NewBoolVar(f'assign_{t}_{j}') for t in trains_list for j in trips_list }
    train_used = {t: model.NewBoolVar(f'used_{t}') for t in trains_list}
    trip_serviced = {j: model.NewBoolVar(f'serviced_{j}') for j in trips_list}
    is_cleaned = {t: model.NewBoolVar(f'cleaned_{t}') for t in trains_list}

    print("  B. Defining hard constraints...")
    for j in trips_list: model.Add(sum(assign[(t, j)] for t in trains_list) == trip_serviced[j])
    trips['start_seconds'], trips['end_seconds'] = pd.to_timedelta(trips['start_time']).dt.total_seconds().astype(int), pd.to_timedelta(trips['end_time']).dt.total_seconds().astype(int)
    for t in trains_list:
        intervals = [model.NewOptionalIntervalVar(trip['start_seconds'], trip['end_seconds'] - trip['start_seconds'], trip['end_seconds'], assign[(t, trip['trip_id'])], f'interval_{t}_{trip["trip_id"]}') for _, trip in trips.iterrows()]
        model.AddNoOverlap(intervals)
    for t in trains_list:
        model.Add(sum(assign[(t, j)] for j in trips_list) > 0).OnlyEnforceIf(train_used[t])
        model.Add(sum(assign[(t, j)] for j in trips_list) == 0).OnlyEnforceIf(train_used[t].Not())

    unavailable_trains = set(job_cards[job_cards['status'] == 'OPEN']['train_id'])
    for _, train in fleet.iterrows():
        t = train['train_id']
        is_unavailable = False
        if t in unavailable_trains: is_unavailable = True; print(f"    - Train {t} is unavailable (OPEN job card).")
        if train['telecom_cert_expiry_date'].date() < PLANNING_DATE.date(): is_unavailable = True; print(f"    - Train {t} is unavailable (Telecom cert expired).")
        if train['stock_cert_expiry_date'].date() < PLANNING_DATE.date(): is_unavailable = True; print(f"    - Train {t} is unavailable (Stock cert expired).")
        if is_unavailable: model.Add(train_used[t] == 0)

    print("  B.2. Defining cleaning constraints...")
    cleaning_intervals, trains_due_for_cleaning = [], []
    cleaning_start_time, cleaning_duration = int(timedelta(hours=23).total_seconds()), int(timedelta(hours=6).total_seconds())
    for _, train in fleet.iterrows():
        t = train['train_id']
        model.AddImplication(is_cleaned[t], train_used[t].Not())
        days_since = (PLANNING_DATE - train['last_deep_clean_date']).days
        if days_since > depot['deep_clean_threshold_days']: trains_due_for_cleaning.append(t); print(f"    - Train {t} is due for cleaning ({days_since} days).")
        else: model.Add(is_cleaned[t] == 0)
        cleaning_intervals.append(model.NewOptionalIntervalVar(cleaning_start_time, cleaning_duration, cleaning_start_time + cleaning_duration, is_cleaned[t], f'cleaning_{t}'))
    model.AddCumulative(cleaning_intervals, [1]*len(cleaning_intervals), depot['cleaning_bays'])

    print("  C. Defining multi-objective function...")
    objective_terms = []
    objective_terms.append(sum(trip_serviced[j] for j in trips_list) * W_TRIP_COVERAGE)
    objective_terms.append(sum(train_used[t] for t in trains_list) * W_ACTIVATION)
    objective_terms.append(sum(is_cleaned[t].Not() for t in trains_due_for_cleaning) * W_CLEANING_PENALTY)
    
    fleet_health_scores = fleet.set_index('train_id')['health_score']
    health_risk = sum(train_used[t] * fleet_health_scores[t] for t in trains_list)
    objective_terms.append(health_risk * W_HEALTH_RISK)
    
    final_mileage_expr = {train['train_id']: int(train['initial_mileage_km']) + sum(assign[(train['train_id'], trip['trip_id'])] * int(trip['distance_km']) for _, trip in trips.iterrows()) for _, train in fleet.iterrows()}
    min_m, max_m = model.NewIntVar(0, 300000, 'min_m'), model.NewIntVar(0, 300000, 'max_m')
    model.AddMinEquality(min_m, list(final_mileage_expr.values())); model.AddMaxEquality(max_m, list(final_mileage_expr.values()))
    mileage_range = model.NewIntVar(0, 100000, 'mileage_range'); model.Add(mileage_range == max_m - min_m)
    objective_terms.append(mileage_range * W_MILEAGE_RANGE)
    
    ad_trains = ad_contracts['train_id'].tolist()
    total_branding_hours = sum(assign[(t, trip['trip_id'])] * trip['duration_hours'] for t in ad_trains for _, trip in trips.iterrows())
    objective_terms.append(total_branding_hours * W_BRANDING)
    
    late_trips = trips[trips['is_late_evening'] == True]
    for terminal_id, required_starts in next_day_starts.items():
        num_ending_at_terminal = sum(assign[(t, trip['trip_id'])] for _, trip in late_trips.iterrows() if trip['stop_id_end'] == terminal_id for t in trains_list)
        mismatch = model.NewIntVar(0, len(fleet), f'mismatch_{terminal_id}')
        model.AddAbsEquality(mismatch, num_ending_at_terminal - required_starts)
        objective_terms.append(mismatch * W_SHUNTING)

    model.Minimize(sum(objective_terms))

    print("  D. Starting solver...")
    solver = cp_model.CpSolver(); solver.parameters.max_time_in_seconds = 60.0
    status = solver.Solve(model)

    print("  E. Processing and saving solution...")
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        schedule_df = pd.DataFrame([{'trip_id': j, 'train_id': t, 'start_time': trips.loc[trips['trip_id'] == j, 'start_time'].iloc[0], 'end_time': trips.loc[trips['trip_id'] == j, 'end_time'].iloc[0]} for t in trains_list for j in trips_list if solver.Value(assign[(t, j)])]).sort_values(by='start_time')
        unserviced_trips = [j for j in trips_list if not solver.Value(trip_serviced[j])]
        
        used_trains_ids = schedule_df['train_id'].unique()
        service_fleet = fleet[fleet['train_id'].isin(used_trains_ids)]
        avg_service_mileage = service_fleet['initial_mileage_km'].mean() if not service_fleet.empty else 0
        MILEAGE_THRESHOLD = 1.15
        
        final_status = []
        for _, train_info in fleet.iterrows():
            t = train_info['train_id']
            reason = "IN SERVICE" if t in used_trains_ids else "STANDBY"
            if solver.Value(is_cleaned[t]): reason = "HELD FOR CLEANING"
            if t in unavailable_trains: reason = "HELD FOR MAINTENANCE (Job Card Open)"
            elif train_info['telecom_cert_expiry_date'].date() < PLANNING_DATE.date(): reason = "HELD (Telecom Cert Expired)"
            elif train_info['stock_cert_expiry_date'].date() < PLANNING_DATE.date(): reason = "HELD (Stock Cert Expired)"

            if reason == "STANDBY":
                if train_info['health_score'] > 0.75: reason = "STANDBY (High Failure Risk)"
                elif train_info['initial_mileage_km'] > (avg_service_mileage * MILEAGE_THRESHOLD): reason = "STANDBY (For Mileage Balancing)"

            final_mileage = solver.Value(final_mileage_expr[t])
            final_status.append({'Train ID': t, 'Status': reason, 'Final Mileage': int(final_mileage), 'Health Score': train_info['health_score']})
        status_df = pd.DataFrame(final_status).sort_values(by=['Status', 'Final Mileage'], ascending=[False, True])
        
        solution_data = {"planning_date": PLANNING_DATE.strftime('%Y-%m-%d'), "solver_status": solver.StatusName(status), "total_trains_used": len(used_trains_ids),"trips_serviced": len(trips_list) - len(unserviced_trips),"trips_unserviced": len(unserviced_trips), "unserviced_trip_ids": unserviced_trips, "induction_ranking": status_df.to_dict(orient='records'), "trip_assignments": schedule_df.to_dict(orient='records')}
        os.makedirs(SOLUTION_DIR, exist_ok=True)
        solution_filename = os.path.join(SOLUTION_DIR, f"{PLANNING_DATE.strftime('%Y-%m-%d')}_solution_details.json")
        with open(solution_filename, 'w') as f: json.dump(solution_data, f, indent=4)
        
        print(f"\n--- Optimal Schedule Found ---")
        print(f"Solution file saved to:\n{solution_filename}")
        if unserviced_trips: print(f"\nWARNING: {len(unserviced_trips)} trips could not be serviced due to resource constraints.")

    else:
        print("Solver failed to find a solution.")

if __name__ == "__main__":
    file_date_str = PLANNING_DATE.strftime('%Y-%m-%d')
    input_file = os.path.join(INPUT_DIR, f"{file_date_str}_input_data.json")
    
    data = load_input_data(input_file)
    if all(d is not None for d in data):
        solve_schedule(*data)