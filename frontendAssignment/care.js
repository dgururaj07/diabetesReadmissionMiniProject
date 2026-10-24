// Care Intervention tab. Loaded after app.js (getEncounter, describeError) and search.js (badge).
const INTERVENTIONS_URL = "http://127.0.0.1:8000/interventions";

const careLookupForm = document.getElementById("care-lookup-form");
const careIdInput = document.getElementById("care_encounter_id");
const careIdError = document.getElementById("care_encounter_id_error");
const careFetchButton = document.getElementById("care-fetch-btn");
const careLookupMessage = document.getElementById("care-lookup-message");
const careSummary = document.getElementById("care-summary");
const careUpdateSection = document.getElementById("care-update");
const careUpdateForm = document.getElementById("care-update-form");
const careStatusSelect = document.getElementById("care_status");
const careAssignedInput = document.getElementById("care_assigned_to");
const careNotesInput = document.getElementById("care_notes");
const careSaveButton = document.getElementById("care-save-btn");
const careUpdateMessage = document.getElementById("care-update-message");

let careEncounterId = null;  // encounter shown on screen; Save always updates this one
let careRequestId = 0;       // only the newest lookup may draw the screen

function setText(id, value) {
  document.getElementById(id).textContent = value === null || value === undefined || value === "" ? "-" : value;
}

function setBadge(id, value, className) {
  const target = document.getElementById(id);
  if (value) {
    target.replaceChildren(badge(value.replaceAll("_", " "), className));
  }
  else {
    target.textContent = "-";
  }
}

function setMessage(element, text, isError) {
  element.textContent = text;
  element.className = isError ? "error" : "success";
}

function formatTime(value) {
  return value ? new Date(value).toLocaleString() : null;
}

// Fill the summary card from GET /encounters/{id}
function showSummary(encounter) {
  setText("sum-encounter-id", `#${encounter.encounter_id}`);
  setText("sum-patient-nbr", `#${encounter.patient_nbr}`);
  setText("sum-risk-score", `${encounter.risk_score} / ${MAX_RISK_SCORE} points`);
  setBadge("sum-risk-level", encounter.risk_level, `risk-${encounter.risk_level.toLowerCase()}`);
  setText("sum-review-reason", encounter.review_reason);
  showIntervention({
    status: encounter.intervention_status, assigned_to: encounter.assigned_to,
    notes: encounter.intervention_notes, updated_at: encounter.intervention_updated_at,
  });
  careSummary.hidden = false;
}

// Intervention part of the summary; also used with the PATCH response after saving
function showIntervention(intervention) {
  setBadge("sum-status", intervention.status, "status");
  setText("sum-assigned-to", intervention.assigned_to);
  setText("sum-notes", intervention.notes);
  setText("sum-updated-at", formatTime(intervention.updated_at));
}

async function lookupEncounter() {
  const value = careIdInput.value.trim();
  const error = value === "" ? "Encounter ID is required."
    : !/^\d+$/.test(value) || Number(value) < 1 ? "Encounter ID must be a positive whole number." : "";
  careIdError.textContent = error;
  careIdInput.classList.toggle("invalid", error !== "");
  if (error !== "") {
    careIdInput.focus();
    return;
  }

  const requestId = ++careRequestId;
  careFetchButton.disabled = true;
  setMessage(careLookupMessage, "Loading...", false);
  careSummary.hidden = true;
  careUpdateSection.hidden = true;
  careUpdateMessage.textContent = "";
  try {
    const encounter = await getEncounter(value);
    if (requestId !== careRequestId) {
      return;  // a newer lookup started while this one was loading
    }
    careEncounterId = encounter.encounter_id;
    showSummary(encounter);
    if (encounter.intervention_id === null) {
      // PATCH would return 404: only MEDIUM/HIGH encounters are queued
      setMessage(careLookupMessage,
        `Encounter ${careEncounterId} is ${encounter.risk_level} risk and has no care intervention, so there is nothing to update.`,
        true);
      return;
    }
    careLookupMessage.textContent = "";
    careStatusSelect.value = encounter.intervention_status;
    careAssignedInput.value = encounter.assigned_to ?? "";
    careNotesInput.value = encounter.intervention_notes ?? "";
    careUpdateSection.hidden = false;
  }
  catch (error) {
    if (requestId !== careRequestId) {
      return;
    }
    // fetch itself throws a TypeError when the server is down or CORS blocks the response
    setMessage(careLookupMessage, error instanceof TypeError
      ? "Could not reach the API. Is the backend running, and is this page opened from http://127.0.0.1:5173?"
      : error.message, true);
  }
  finally {
    if (requestId === careRequestId) {
      careFetchButton.disabled = false;
    }
  }
}

// Status is always sent. Empty text fields are left out, because the API keeps the old value for a missing field.
function readCareUpdate() {
  const update = { status: careStatusSelect.value };
  const assignedTo = careAssignedInput.value.trim();
  const notes = careNotesInput.value.trim();
  if (assignedTo !== "") {
    update.assigned_to = assignedTo;
  }
  if (notes !== "") {
    update.notes = notes;
  }
  return update;
}

async function saveIntervention() {
  careSaveButton.disabled = true;  // stop double clicks from sending two updates
  setMessage(careUpdateMessage, "Saving...", false);
  try {
    const response = await fetch(`${INTERVENTIONS_URL}/${careEncounterId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(readCareUpdate()),
    });
    const body = await response.json();
    if (!response.ok) {
      throw new Error(describeError(response.status, body));
    }
    showIntervention(body);
    careAssignedInput.value = body.assigned_to ?? "";
    careNotesInput.value = body.notes ?? "";
    setMessage(careUpdateMessage, `Saved at ${formatTime(body.updated_at)}.`, false);
  }
  catch (error) {
    setMessage(careUpdateMessage, error instanceof TypeError
      ? "Could not reach the API. Is the backend running?"
      : error.message, true);
  }
  finally {
    careSaveButton.disabled = false;
  }
}

// Called from the Search tab: open this tab and load the clicked encounter
function openCareFor(encounterId) {
  careIdInput.value = encounterId;
  selectTab("care", false);
  lookupEncounter();
}

careLookupForm.addEventListener("submit", function (event) {
  event.preventDefault();
  lookupEncounter();
});

careUpdateForm.addEventListener("submit", function (event) {
  event.preventDefault();
  saveIntervention();
});
