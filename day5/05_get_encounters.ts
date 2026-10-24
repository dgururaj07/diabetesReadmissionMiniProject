async function loadPatients() {
    try {
        const response = await fetch("http://127.0.0.1:8000/encounters");
        if (!response.ok) {
            throw new Error(`Request failed with status ${response.status}`);
        }
        const patients = await response.json();
        console.log(patients);
    }
    catch (error) {
        console.error("Error loading patients:", error);
    }
}


loadPatients();