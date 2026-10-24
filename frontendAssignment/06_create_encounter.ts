async function createEncounter(encounter: object) {
    try {
        const response = await fetch("http://127.0.0.1:8000/encounters", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(encounter),
        });
        if (!response.ok) {
            // 400 / 422 / 503 send their reason in the body as { detail: ... }
            const error = await response.json();
            throw new Error(`Request failed with status ${response.status}: ${JSON.stringify(error.detail)}`);
        }
        const created = await response.json();
        console.log(created);
        return created;
    }
    catch (error) {
        console.error("Error creating encounter:", error);
    }
}


createEncounter({
    patient_nbr: 98888,
    age: "[60-70)",
    time_in_hospital: 8,
    number_inpatient: 3,
    number_emergency: 2,
    number_outpatient: 3,
    num_medications: 22,
    num_lab_procedures: 45,
    num_procedures: 2,
    admission_type_id: 1,
    discharge_disposition_id: 1,
    readmitted: "<30",
});
