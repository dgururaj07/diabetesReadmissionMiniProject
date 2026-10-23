// Empty export makes this file a module, so its top-level names don't clash with other files' globals
export {};

type RiskLevel = "LOW" | "MEDIUM" | "HIGH";
type Readmitted = "<30" | ">30" | "NO";
type InterventionStatus = "PENDING_REVIEW" | "ASSIGNED" | "CONTACTED" | "FOLLOW_UP_SCHEDULED" | "CLOSED";

// Same shape as in 01_encounter_api.ts: one row of patient_encounters
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
    created_at: string
}

// GET /encounters/{id}: every Encounter field plus the intervention (all null for LOW-risk encounters)
interface EncounterDetail extends Encounter {
    intervention_id: number | null,
    intervention_status: InterventionStatus | null,
    assigned_to: string | null,
    intervention_notes: string | null,
    intervention_created_at: string | null,
    intervention_updated_at: string | null
}

async function getEncounter(encounterId: number): Promise<EncounterDetail | null> {
    const baseUrl = "http://127.0.0.1:8000";
    const response = await fetch(`${baseUrl}/encounters/${encounterId}`);
    if (response.status === 404) {
        return null;   // encounter doesn't exist: an expected case, not a crash
    }
    if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`);
    }
    return await response.json();
}

async function showEncounter(encounterId: number) {
    const encounter = await getEncounter(encounterId);
    if (encounter === null) {
        console.log(`Encounter ${encounterId} not found`);
        return;
    }
    console.log(encounter.encounter_id, encounter.risk_level, encounter.risk_score, encounter.review_reason);

    // Checking the field itself narrows it from `InterventionStatus | null` to `InterventionStatus`
    if (encounter.intervention_status === null) {
        console.log("  No care intervention (LOW risk)");
    } else {
        console.log("  Intervention:", encounter.intervention_status, encounter.assigned_to, encounter.intervention_notes);
    }
}

async function main() {
    await showEncounter(12522);        // change to an id from your data
    await showEncounter(999999);   // does not exist -> "not found"
}

main();
