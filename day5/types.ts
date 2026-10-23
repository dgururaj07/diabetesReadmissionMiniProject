// Types only, no code: mirrors the FastAPI backend (backend/api/models.py and the SQL schema).

export type RiskLevel = "LOW" | "MEDIUM" | "HIGH";
export type Readmitted = "<30" | ">30" | "NO";
export type InterventionStatus = "PENDING_REVIEW" | "ASSIGNED" | "CONTACTED" | "FOLLOW_UP_SCHEDULED" | "CLOSED";

// One row of patient_encounters, as returned by GET /encounters
export interface Encounter {
    encounter_id: number,
    patient_nbr: number,
    age: string | null,
    time_in_hospital: number | null,
    number_inpatient: number | null,
    number_emergency: number | null,
    number_outpatient: number | null,
    num_medications: number | null,
    num_lab_procedures: number | null,
    num_procedures: number | null,
    admission_type_id: number | null,
    discharge_disposition_id: number | null,
    readmitted: Readmitted | null,
    risk_score: number,
    risk_level: RiskLevel,
    review_reason: string | null,
    created_at: string   // ISO timestamp string
}

// GET /encounters/{id}: every Encounter field plus the intervention (all null for LOW-risk encounters)
export interface EncounterDetail extends Encounter {
    intervention_id: number | null,
    intervention_status: InterventionStatus | null,
    assigned_to: string | null,
    intervention_notes: string | null,
    intervention_created_at: string | null,
    intervention_updated_at: string | null
}

// One item of GET /care-queue. Every queued encounter has an intervention, so these are never null.
export interface CareQueueItem {
    encounter_id: number,
    patient_nbr: number,
    age: string | null,
    risk_score: number,
    risk_level: Exclude<RiskLevel, "LOW">,   // only "MEDIUM" | "HIGH" are queued
    review_reason: string | null,
    intervention_id: number,
    status: InterventionStatus,
    assigned_to: string | null,
    notes: string | null,
    created_at: string,   // the INTERVENTION's created_at
    updated_at: string
}

// Paging shared by the list endpoints: limit 1-500 (default 50), offset >= 0 (default 0)
export interface PageParams {
    limit?: number,
    offset?: number
}

export interface EncounterParams extends PageParams {
    risk_level?: RiskLevel,
    readmitted?: Readmitted
}

export interface CareQueueParams extends PageParams {
    risk_level?: RiskLevel,
    status?: InterventionStatus,
    assigned_to?: string
}
