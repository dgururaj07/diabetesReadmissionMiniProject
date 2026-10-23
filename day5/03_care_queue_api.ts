// Empty export makes this file a module, so its top-level names don't clash with other files' globals
export {};

type RiskLevel = "LOW" | "MEDIUM" | "HIGH";
type InterventionStatus = "PENDING_REVIEW" | "ASSIGNED" | "CONTACTED" | "FOLLOW_UP_SCHEDULED" | "CLOSED";

// One item of GET /care-queue. The queue only holds encounters WITH an intervention (an inner JOIN),
// so intervention_id and status are never null, unlike in GET /encounters/{id}.
interface CareQueueItem {
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
    created_at: string,   // the INTERVENTION's created_at (not the encounter's)
    updated_at: string
}

// Optional query parameters; `?` means the caller may leave them out
interface CareQueueParams {
    risk_level?: RiskLevel,
    status?: InterventionStatus,
    assigned_to?: string,
    limit?: number,    // 1-500, API default 50
    offset?: number    // >= 0, API default 0
}

async function getCareQueue(params: CareQueueParams = {}): Promise<CareQueueItem[]> {
    const baseUrl = "http://127.0.0.1:8000";
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
        if (value !== undefined) {
            query.append(key, String(value));
        }
    }
    const response = await fetch(`${baseUrl}/care-queue?${query}`);
    if (!response.ok) {
        // 422 = invalid parameter, for example limit=0 or an unknown status
        throw new Error(`Request failed with status ${response.status}`);
    }
    return await response.json();
}

async function main() {
    const queue = await getCareQueue({ risk_level: "HIGH", limit: 5 });
    console.log(`${queue.length} items`);
    for (const item of queue) {
        console.log(item.encounter_id, item.risk_level, item.status, item.assigned_to ?? "(unassigned)", item.created_at);
    }
}

main();
