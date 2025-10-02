/**
 * Shared code between client and server
 * Useful to share types between client and server
 * and/or small pure JS functions that can be used on both client and server
 */

/**
 * Example response type for /api/demo
 */
export interface DemoResponse {
  message: string;
}

/**
 * Train scheduling related types
 */
export interface Train {
  train_id: string;
  initial_mileage_km: number;
  health_score: number;
  last_deep_clean_date: string;
  telecom_cert_expiry_date: string;
  stock_cert_expiry_date: string;
  signal_cert_expiry_km: number;
}

export interface InductionRanking {
  "Train ID": string;
  Status: string;
  "Final Mileage": number;
  "Health Score": number;
}

export interface TripAssignment {
  trip_id: string;
  train_id: string;
  start_time: string;
  end_time: string;
}

export interface Constraint {
  name: string;
  description: string;
  trains_affected: number;
  status: "ACTIVE" | "SATISFIED" | "VIOLATED";
}

export interface AuditEvent {
  timestamp: string;
  event: string;
  details: string;
}

export interface ScheduleGenerationRequest {
  planning_date: string;
  fleet_data?: Train[];
  constraints?: any;
}

export interface ScheduleGenerationResponse {
  success: boolean;
  planning_date: string;
  input_data: any;
  solution: {
    planning_date: string;
    solver_status: string;
    total_trains_used: number;
    trips_serviced: number;
    trips_unserviced: number;
    unserviced_trip_ids: string[];
    induction_ranking: InductionRanking[];
    trip_assignments: TripAssignment[];
  };
  constraints_applied: Constraint[];
  audit_trail: AuditEvent[];
}

export interface ScheduleHistoryResponse {
  schedules: Array<{
    planning_date: string;
    solver_status: string;
    total_trains_used: number;
    trips_serviced: number;
    trips_unserviced: number;
    created_at: string;
  }>;
}

export interface ScheduleDetailsResponse {
  planning_date: string;
  solution: any;
  input_data: any;
  constraints_applied: Constraint[];
  audit_trail: AuditEvent[];
}
