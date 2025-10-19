import json
from ortools.sat.python import cp_model
from datetime import datetime, date
import os

def solve_advanced_schedule(input_data):
    """
    Solves the train scheduling problem with a comprehensive multi-objective function.
    This version includes the final fix for the MODEL_INVALID error by simplifying the cleaning constraint.
    """
    
    # --- 1. DATA PREPARATION ---
    trains = input_data['trains']
    trips = input_data['trips']
    shunting_distances_data = input_data['shunting_distances']
    average_fleet_mileage = input_data['average_fleet_mileage']
    depot_resources = input_data['depot_resources']
    
    train_ids = [t['train_id'] for t in trains]
    trip_ids = [t['trip_id'] for t in trips]
    
    train_map = {t['train_id']: t for t in trains}
    trip_map = {t['trip_id']: t for t in trips}
    
    all_stop_ids = set()
    for r in shunting_distances_data:
        all_stop_ids.add(r['from_stop_id']); all_stop_ids.add(r['to_stop_id'])
    for t in trips:
        all_stop_ids.add(t['start_stop_id']); all_stop_ids.add(t['end_stop_id'])
    
    sorted_stop_ids = sorted(list(all_stop_ids))
    stop_id_to_int = {stop_id: i for i, stop_id in enumerate(sorted_stop_ids)}
    
    for trip in trips:
        start_h, start_m, start_s = map(int, trip['start_time'].split(':'))
        trip['start_sec'] = (start_h * 3600) + (start_m * 60) + start_s
        end_h, end_m, end_s = map(int, trip['end_time'].split(':'))
        trip['end_sec'] = (end_h * 3600) + (end_m * 60) + end_s
        if trip['end_sec'] < trip['start_sec']:
            trip['end_sec'] += 24 * 3600

    HORIZON = 86400 * 2 

    # --- 2. MODEL CREATION & VARIABLES ---
    model = cp_model.CpModel()
    assignments = { (t_id, p_id): model.NewBoolVar(f'assign_{t_id}_{p_id}') for t_id in train_ids for p_id in trip_ids }

    # --- 3. HARD CONSTRAINTS ---
    for p_id in trip_ids:
        model.AddAtMostOne(assignments[(t_id, p_id)] for t_id in train_ids)

    for t_id in train_ids:
        for i in range(len(trips)):
            for j in range(i + 1, len(trips)):
                trip1, trip2 = trips[i], trips[j]
                if max(trip1['start_sec'], trip2['start_sec']) < min(trip1['end_sec'], trip2['end_sec']):
                    model.AddBoolOr([assignments[(t_id, trip1['trip_id'])].Not(), assignments[(t_id, trip2['trip_id'])].Not()])

    trains_requiring_cleaning = [t for t in trains if t.get('cleaning_required_hours', 0) > 0]
    for t_id in train_ids:
        train = train_map[t_id]
        # Forbid trains from service if they have job cards, expired certs, OR are scheduled for cleaning
        if train['has_open_job_card'] or not train['is_fully_certified'] or train in trains_requiring_cleaning:
            for p_id in trip_ids:
                model.Add(assignments[(t_id, p_id)] == 0)

    # --- Cleaning Bay Capacity Constraint ---
    cleaning_bays_capacity = depot_resources.get("Muttom Depot", {}).get("cleaning_bays", 0)
    cleaning_intervals = []
    
    for train in trains_requiring_cleaning:
        t_id = train['train_id']
        duration_sec = int(train['cleaning_required_hours'] * 3600)
        
        start_var = model.NewIntVar(0, HORIZON - duration_sec, f'clean_start_{t_id}')
        end_var = model.NewIntVar(0, HORIZON, f'clean_end_{t_id}')
        interval_var = model.NewIntervalVar(start_var, duration_sec, end_var, f'clean_interval_{t_id}')
        cleaning_intervals.append(interval_var)

    if cleaning_intervals and cleaning_bays_capacity > 0:
        model.AddCumulative(cleaning_intervals, [1] * len(cleaning_intervals), cleaning_bays_capacity)

    # --- 4. MULTI-OBJECTIVE CALCULATIONS ---
    total_trips_serviced = sum(assignments.values())

    num_stops = len(sorted_stop_ids)
    distance_matrix = [[0] * num_stops for _ in range(num_stops)]
    for r in shunting_distances_data:
        from_idx, to_idx = stop_id_to_int.get(r['from_stop_id']), stop_id_to_int.get(r['to_stop_id'])
        if from_idx is not None and to_idx is not None:
            distance_matrix[from_idx][to_idx] = int(r['distance_km'] * 10)
    flat_distance_matrix = [item for sublist in distance_matrix for item in sublist]
    
    train_shunting_distances = []
    for t_id in train_ids:
        is_train_used = model.NewBoolVar(f'used_{t_id}')
        model.Add(sum(assignments[(t_id, p['trip_id'])] for p in trips) > 0).OnlyEnforceIf(is_train_used)
        model.Add(sum(assignments[(t_id, p['trip_id'])] for p in trips) == 0).OnlyEnforceIf(is_train_used.Not())
        min_start_time, max_end_time = model.NewIntVar(0, HORIZON, f'min_start_{t_id}'), model.NewIntVar(0, HORIZON, f'max_end_{t_id}')
        potential_start_times, potential_end_times = [], []
        for p in trips:
            start_var, end_var = model.NewIntVar(0, HORIZON, f'start_var_{t_id}_{p["trip_id"]}'), model.NewIntVar(0, HORIZON, f'end_var_{t_id}_{p["trip_id"]}')
            model.Add(start_var == p['start_sec']).OnlyEnforceIf(assignments[(t_id, p['trip_id'])])
            model.Add(start_var == HORIZON).OnlyEnforceIf(assignments[(t_id, p['trip_id'])].Not())
            potential_start_times.append(start_var)
            model.Add(end_var == p['end_sec']).OnlyEnforceIf(assignments[(t_id, p['trip_id'])])
            model.Add(end_var == 0).OnlyEnforceIf(assignments[(t_id, p['trip_id'])].Not())
            potential_end_times.append(end_var)
        model.AddMinEquality(min_start_time, potential_start_times)
        model.AddMaxEquality(max_end_time, potential_end_times)
        first_trip_loc_idx, last_trip_loc_idx = model.NewIntVar(0, num_stops - 1, f'first_loc_idx_{t_id}'), model.NewIntVar(0, num_stops - 1, f'last_loc_idx_{t_id}')
        potential_first_locs, potential_last_locs = [], []
        for p in trips:
            is_first, is_last = model.NewBoolVar(f'is_first_{t_id}_{p["trip_id"]}'), model.NewBoolVar(f'is_last_{t_id}_{p["trip_id"]}')
            min_matches, max_matches = model.NewBoolVar(f'min_match_{t_id}_{p["trip_id"]}'), model.NewBoolVar(f'max_match_{t_id}_{p["trip_id"]}')
            model.Add(min_start_time == p['start_sec']).OnlyEnforceIf(min_matches)
            model.Add(min_start_time != p['start_sec']).OnlyEnforceIf(min_matches.Not())
            model.AddBoolAnd([assignments[(t_id, p['trip_id'])], min_matches]).OnlyEnforceIf(is_first)
            model.Add(max_end_time == p['end_sec']).OnlyEnforceIf(max_matches)
            model.Add(max_end_time != p['end_sec']).OnlyEnforceIf(max_matches.Not())
            model.AddBoolAnd([assignments[(t_id, p['trip_id'])], max_matches]).OnlyEnforceIf(is_last)
            potential_first_locs.append(is_first * stop_id_to_int.get(p['start_stop_id'], 0))
            potential_last_locs.append(is_last * stop_id_to_int.get(p['end_stop_id'], 0))
        model.Add(first_trip_loc_idx == sum(potential_first_locs))
        model.Add(last_trip_loc_idx == sum(potential_last_locs))
        shunting_dist_for_train = model.NewIntVar(0, 500, f'shunt_dist_{t_id}')
        index_var = model.NewIntVar(0, len(flat_distance_matrix) - 1, f'index_{t_id}')
        model.Add(index_var == last_trip_loc_idx * num_stops + first_trip_loc_idx)
        model.AddElement(index_var, flat_distance_matrix, shunting_dist_for_train)
        final_shunting_dist = model.NewIntVar(0, 500, f'final_shunt_dist_{t_id}')
        model.Add(final_shunting_dist == shunting_dist_for_train).OnlyEnforceIf(is_train_used)
        model.Add(final_shunting_dist == 0).OnlyEnforceIf(is_train_used.Not())
        train_shunting_distances.append(final_shunting_dist)
    total_shunting_distance = sum(train_shunting_distances)
    mileage_deviations = []
    for t_id in train_ids:
        initial_mileage = int(train_map[t_id]['mileage'])
        mileage_from_trips = sum(int(trip_map[p_id]['distance_km']) * assignments[(t_id, p_id)] for p_id in trip_ids)
        final_mileage = model.NewIntVar(initial_mileage, initial_mileage + 20000, f'final_mileage_{t_id}')
        model.Add(final_mileage == initial_mileage + mileage_from_trips)
        deviation = model.NewIntVar(0, 100000, f'dev_{t_id}')
        model.AddAbsEquality(deviation, final_mileage - int(average_fleet_mileage))
        mileage_deviations.append(deviation)
    total_mileage_deviation = sum(mileage_deviations)
    branding_hours_scaled = []
    for t_id in train_ids:
        if train_map[t_id]['has_branding_contract']:
            duration_in_seconds = sum( (trip_map[p_id]['end_sec'] - trip_map[p_id]['start_sec']) * assignments[(t_id, p_id)] for p_id in trip_ids )
            branding_hours_scaled.append(duration_in_seconds)
    total_branding_duration_scaled = sum(branding_hours_scaled)

    # --- 5. FINAL WEIGHTED OBJECTIVE FUNCTION ---
    model.Maximize(
        total_trips_serviced * 100000
        - total_shunting_distance * 100
        - total_mileage_deviation * 1
        + total_branding_duration_scaled
    )

    # --- 6. SOLVER INVOCATION ---
    print("Solving the schedule with full multi-objective function...")
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 180.0
    status = solver.Solve(model)
    print(f"Solver status: {solver.StatusName(status)}")

    # --- 7. PROCESS AND SAVE SOLUTION ---
    if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        print("Solution found. Processing output...")
        solved_shunting_distances = {train_ids[i]: solver.Value(train_shunting_distances[i]) / 10.0 for i in range(len(train_ids))}
        
        trip_assignments, serviced_trips = [], set()
        train_usage = {t_id: [] for t_id in train_ids}

        for t_id in train_ids:
            for p_id in trip_ids:
                if solver.Value(assignments[(t_id, p_id)]):
                    trip_info = trip_map[p_id]
                    trip_assignments.append({ 'trip_id': p_id, 'train_id': t_id, 'start_time': trip_info['start_time'], 'end_time': trip_info['end_time'] })
                    serviced_trips.add(p_id)
                    train_usage[t_id].append(trip_info)
        
        induction_ranking = []
        for t_id in train_ids:
            train_info = train_map[t_id]
            actual_shunting_km = solved_shunting_distances.get(t_id, 0)
            
            status_text, reason = "", ""
            if train_info['has_open_job_card']:
                status_text, reason = "HELD FOR MAINTENANCE", "Open Job Card from Maximo"
            elif not train_info['is_fully_certified']:
                status_text, reason = "HELD FOR CERTIFICATION", "One or more fitness certificates have expired"
            elif train_info.get('cleaning_required_hours', 0) > 0:
                 status_text, reason = "HELD FOR CLEANING", f"Scheduled for {train_info['cleaning_required_hours']} hour cleaning task"
            elif train_usage[t_id]:
                status_text, reason = "IN SERVICE", f"Assigned to {len(train_usage[t_id])} trips"
            else:
                status_text, reason = "STANDBY", "Optimized for shunting/mileage or not required for service"

            final_mileage_val = train_info['mileage'] + sum(t['distance_km'] for t in train_usage[t_id])

            induction_ranking.append({
                "Train ID": t_id, "Status": status_text, "Reason": reason,
                "Shunting Distance (km)": actual_shunting_km,
                "Final Mileage": f"{final_mileage_val:.3f}",
                "Health Score": train_info.get('anomaly_score', 0.5)
            })
        
        total_shunting_km = sum(solved_shunting_distances.values())
        output_solution = {
            'planning_date': input_data['planning_date'],
            'solver_status': solver.StatusName(status),
            'total_shunting_km': round(total_shunting_km, 2),
            'total_mileage_deviation': round(solver.Value(total_mileage_deviation), 2) if status in [cp_model.OPTIMAL, cp_model.FEASIBLE] else 'N/A',
            'trips_serviced': len(serviced_trips),
            'trips_unserviced': len(trip_ids) - len(serviced_trips),
            'induction_ranking': induction_ranking,
            'trip_assignments': trip_assignments
        }

        output_filename = f"daily_solution/{input_data['planning_date']}_solution_details.json"
        os.makedirs("daily_solution", exist_ok=True)
        with open(output_filename, 'w') as f:
            json.dump(output_solution, f, indent=4)
        print(f"Solution saved to {output_filename}")
        
    else:
        print("No solution found.")

if __name__ == '__main__':
    print("Starting Advanced Schedule Solver...")
    planning_date = date.today()
    planning_date_str = planning_date.strftime('%Y-%m-%d')
    input_file_path = f'daily_input/{planning_date_str}_input_data.json'
    
    print(f"Loading input data from {input_file_path}...")
    try:
        with open(input_file_path, 'r') as f:
            input_data = json.load(f)
        solve_advanced_schedule(input_data)
    except FileNotFoundError:
        print(f"Error: Input file not found at {input_file_path}")

