import { getCareQueue, getEncounter, getEncounters } from "./apiClient.ts";

async function main() {
    const encounters = await getEncounters({ risk_level: "HIGH", limit: 3 });
    console.log("GET /encounters");
    for (const e of encounters) {
        console.log(" ", e.encounter_id, e.risk_level, e.risk_score, e.review_reason);
    }

    console.log("GET /encounters/{id}");
    for (const id of [12522, 999999]) {   // change 12522 to an id from your data
        const detail = await getEncounter(id);
        if (detail === null) {
            console.log(`  Encounter ${id} not found`);
        } else {
            console.log(" ", detail.encounter_id, detail.risk_level, detail.intervention_status ?? "(no intervention)");
        }
    }

    const queue = await getCareQueue({ risk_level: "HIGH", limit: 3 });
    console.log("GET /care-queue");
    for (const item of queue) {
        console.log(" ", item.encounter_id, item.status, item.assigned_to ?? "(unassigned)", item.created_at);
    }
}

main();
