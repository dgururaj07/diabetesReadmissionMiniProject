const API_URL = "http://127.0.0.1:8000/encounters";

// Number fields sent to the API; empty ones are left out so the backend defaults apply
const NUMBER_FIELDS = ["time_in_hospital", "number_inpatient", "number_emergency", "number_outpatient",
  "num_medications", "num_lab_procedures", "num_procedures", "admission_type_id", "discharge_disposition_id"];

// Table columns, in the same order as the <th> cells in index.html
const COLUMNS = ["encounter_id", "patient_nbr", "age", "time_in_hospital", "number_inpatient", "number_emergency",
  "number_outpatient", "num_medications", "num_lab_procedures", "num_procedures", "readmitted", "risk_score",
  "risk_level", "review_reason", "intervention_status", "assigned_to", "intervention_notes", "created_at"];

const form = document.getElementById("encounter-form");
const button = document.getElementById("add-encounter-btn");
const message = document.getElementById("form-message");
const patientInput = document.getElementById("patient_nbr");
const patientError = document.getElementById("patient_nbr_error");
const tableBody = document.getElementById("encounter-list");

// Returns an error message, or "" if the patient number is valid
function validatePatientNumber() {
  const value = patientInput.value.trim();
  if (value === "") {
    return "Patient number is required.";
  }
  // Must be a whole number greater than zero (DB column is a BIGINT id)
  if (!/^\d+$/.test(value) || Number(value) < 1) {
    return "Patient number must be a positive whole number.";
  }
  return "";
}

// Show (or clear) the message and mark the field as invalid for styling
function showPatientError() {
  const error = validatePatientNumber();
  patientError.textContent = error;
  patientInput.classList.toggle("invalid", error !== "");
  return error === "";
}

// Build the JSON body from the form fields
function readForm() {
  const encounter = {
    patient_nbr: Number(patientInput.value.trim()),
    readmitted: form.readmitted.value,
  };
  if (form.age.value !== "") {
    encounter.age = form.age.value;
  }
  for (const field of NUMBER_FIELDS) {
    const value = form[field].value;
    if (value !== "") {
      encounter[field] = Number(value);
    }
  }
  return encounter;
}

// Turn the API's error body into readable text. 400/503 send a string, 422 sends a list of field errors.
function describeError(status, body) {
  if (Array.isArray(body.detail)) {
    return body.detail.map((item) => `${item.loc[item.loc.length - 1]}: ${item.msg}`).join("; ");
  }
  return body.detail || `Request failed with status ${status}`;
}

async function createEncounter(encounter) {
  const response = await fetch(API_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(encounter),
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(describeError(response.status, body));
  }
  return body;
}

// GET /encounters/{id} adds the intervention fields the POST response leaves out (assigned_to, intervention_notes)
async function getEncounter(encounterId) {
  const response = await fetch(`${API_URL}/${encounterId}`);
  const body = await response.json();
  if (!response.ok) {
    throw new Error(describeError(response.status, body));
  }
  return body;
}

// Prefer the full detail; if that request fails the encounter is still saved, so show what the POST returned
async function loadDetail(created) {
  try {
    return await getEncounter(created.encounter_id);
  }
  catch (error) {
    console.error("Error loading encounter detail:", error);
    return { ...created, intervention_status: created.status };
  }
}

function formatCell(column, value) {
  if (value === null || value === undefined) {
    return "-";
  }
  if (column === "created_at") {
    return new Date(value).toLocaleString();
  }
  return String(value);
}

// Add the created encounter as the first row. textContent (not innerHTML) keeps any typed text from running as HTML.
function addRow(encounter) {
  const emptyRow = document.getElementById("empty-row");
  if (emptyRow) {
    emptyRow.remove();
  }
  const row = document.createElement("tr");
  for (const column of COLUMNS) {
    const cell = document.createElement("td");
    cell.textContent = formatCell(column, encounter[column]);
    if (column === "risk_level") {
      cell.className = `risk risk-${encounter.risk_level.toLowerCase()}`;
    }
    row.appendChild(cell);
  }
  tableBody.prepend(row);
}

function showMessage(text, isError) {
  message.textContent = text;
  message.className = isError ? "error" : "success";
}

form.addEventListener("submit", async function (event) {
  // Always stop the browser's own page reload; we send the data with fetch instead
  event.preventDefault();
  if (!showPatientError()) {
    patientInput.focus();
    return;
  }

  button.disabled = true;  // stop double clicks from creating two encounters
  showMessage("Saving...", false);
  try {
    const created = await createEncounter(readForm());
    addRow(await loadDetail(created));
    showMessage(`Encounter ${created.encounter_id} added: ${created.risk_level} risk (score ${created.risk_score}).`,
      false);
    form.reset();
    patientInput.focus();
  }
  catch (error) {
    // fetch itself throws a TypeError when the server is down or CORS blocks the response
    const text = error instanceof TypeError
      ? "Could not reach the API. Is the backend running, and is this page opened from http://127.0.0.1:5173?"
      : error.message;
    showMessage(text, true);
  }
  finally {
    button.disabled = false;
  }
});

// Re-check while typing so the message disappears once it is fixed
patientInput.addEventListener("input", showPatientError);
