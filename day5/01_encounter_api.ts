// Empty export makes this file a module, so its top-level names don't clash with other files' globals
export {};

// Allowed values come from the backend: risk_level has a CHECK constraint, readmitted is the historical outcome
type RiskLevel = "LOW" | "MEDIUM" | "HIGH";
type Readmitted = "<30" | ">30" | "NO";

// One row returned by GET /encounters (SELECT * FROM patient_encounters).
// Columns that can be NULL in the database are typed `| null`.
interface Encounter {
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
    created_at: string   // timestamp arrives as an ISO string in JSON, e.g. "2026-01-01T00:00:00"
}

async function getEncounters(): Promise<Encounter[]> {
    const baseUrl = "http://127.0.0.1:8000";
    const response = await fetch(`${baseUrl}/encounters?limit=5`);
    if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`);
    }
    // response.json() is untyped (any); the return type tells TypeScript what we expect
    return await response.json();
}

async function main() {
    const encounters = await getEncounters();
    for (const encounter of encounters) {
        console.log(encounter.encounter_id, encounter.risk_level, encounter.risk_score, encounter.review_reason);
    }
}

main();
