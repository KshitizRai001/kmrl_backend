#!/usr/bin/env python3
"""
Setup script for the Advanced Metro Scheduling Model

This script sets up the environment and runs the complete scheduling pipeline.
"""

import os
import sys
import subprocess
import json
from datetime import datetime, timedelta

def install_requirements():
    """Install required Python packages"""
    print("Installing Python requirements...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("[OK] Requirements installed successfully")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to install requirements: {e}")
        return False
    return True

def train_anomaly_model():
    """Train the anomaly detection model"""
    print("Training anomaly detection model...")
    try:
        subprocess.check_call([sys.executable, "00_train_anomaly_model.py"])
        print("[OK] Anomaly model trained successfully")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to train anomaly model: {e}")
        return False
    return True

def generate_sample_schedule(date_str=None):
    """Generate a sample schedule for testing"""
    if date_str is None:
        date_str = datetime.now().strftime('%Y-%m-%d')
    
    print(f"Generating sample schedule for {date_str}...")
    try:
        # Generate input data
        subprocess.check_call([sys.executable, "01_generate_advanced_input.py", date_str])
        print("[OK] Input data generated")
        
        # Solve schedule
        subprocess.check_call([sys.executable, "02_solve_advanced_schedule.py", date_str])
        print("[OK] Schedule solved successfully")
        
        # Verify output files exist
        input_file = f"daily_input/{date_str}_input_data.json"
        solution_file = f"daily_solution/{date_str}_solution_details.json"
        
        if os.path.exists(input_file) and os.path.exists(solution_file):
            print(f"[OK] Schedule files created: {input_file}, {solution_file}")
            return True
        else:
            print("[ERROR] Schedule files not found")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to generate schedule: {e}")
        return False

def verify_setup():
    """Verify the setup is working correctly"""
    print("Verifying setup...")
    
    # Check if model file exists
    if os.path.exists("anomaly_model.joblib"):
        print("[OK] Anomaly model file found")
    else:
        print("[ERROR] Anomaly model file not found")
        return False
    
    # Check if sample data exists
    today = datetime.now().strftime('%Y-%m-%d')
    input_file = f"daily_input/{today}_input_data.json"
    solution_file = f"daily_solution/{today}_solution_details.json"
    
    if os.path.exists(input_file) and os.path.exists(solution_file):
        print("[OK] Sample schedule files found")
        
        # Load and display summary
        try:
            with open(solution_file, 'r') as f:
                solution = json.load(f)
            
            print(f"  - Solver Status: {solution.get('solver_status', 'Unknown')}")
            print(f"  - Trains Used: {solution.get('total_trains_used', 0)}")
            print(f"  - Trips Serviced: {solution.get('trips_serviced', 0)}")
            print(f"  - Trips Unserviced: {solution.get('trips_unserviced', 0)}")
            
        except Exception as e:
            print(f"[ERROR] Failed to read solution file: {e}")
            return False
    else:
        print("[ERROR] Sample schedule files not found")
        return False
    
    return True

def main():
    """Main setup function"""
    print("=" * 60)
    print("Advanced Metro Scheduling Model Setup")
    print("=" * 60)
    
    # Change to the script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    success = True
    
    # Step 1: Install requirements
    if not install_requirements():
        success = False
    
    # Step 2: Train anomaly model
    if success and not train_anomaly_model():
        success = False
    
    # Step 3: Generate sample schedule
    if success and not generate_sample_schedule():
        success = False
    
    # Step 4: Verify setup
    if success and not verify_setup():
        success = False
    
    print("=" * 60)
    if success:
        print("[SUCCESS] Setup completed successfully!")
        print("\nYou can now:")
        print("1. Start the web application: pnpm dev")
        print("2. Generate schedules via the web interface")
        print("3. View schedule history and details")
    else:
        print("[FAILED] Setup failed. Please check the errors above.")
        sys.exit(1)
    print("=" * 60)

if __name__ == "__main__":
    main()
