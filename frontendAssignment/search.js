// Search tab. Loaded after app.js, so it reuses describeError() from there.
const SEARCH_URL = "http://127.0.0.1:8000/patients/search";
const PAGE_SIZE = 50;
const MAX_RISK_SCORE = 8;

const searchForm = document.getElementById("search-form");
const searchButton = document.getElementById("search-btn");
const searchPatientInput = document.getElementById("search_patient_nbr");
const searchPatientError = document.getElementById("search_patient_nbr_error");
const searchLevelSelect = document.getElementById("search_risk_level");
const searchScoreInput = document.getElementById("search_risk_score");
const searchScoreError = document.getElementById("search_risk_score_error");
const chips = document.querySelectorAll(".chip");
const resultsBody = document.getElementById("search-results");
const resultsSummary = document.getElementById("results-summary");
const prevPageButton = document.getElementById("prev-page-btn");
const nextPageButton = document.getElementById("next-page-btn");
const pageInfo = document.getElementById("page-info");

let currentFilters = {};  // filters of the results on screen; Refresh and paging reuse them
let currentOffset = 0;
let searchRequestId = 0;  // only the newest request may draw the table
let searchLoaded = false;

// Show (or clear) a field's message and red border; returns true when the field is valid
function setFieldError(input, errorSpan, text) {
  errorSpan.textContent = text;
  input.classList.toggle("invalid", text !== "");
  return text === "";
}

// Read the three filters; returns null (and shows the messages) if any is invalid. Empty fields are left out.
function readSearchFilters() {
  const filters = {};
  const patient = searchPatientInput.value.trim();
  const score = searchScoreInput.value.trim();

  const patientOk = setFieldError(searchPatientInput, searchPatientError,
    patient !== "" && (!/^\d+$/.test(patient) || Number(patient) < 1)
      ? "Patient number must be a positive whole number." : "");
  const scoreOk = setFieldError(searchScoreInput, searchScoreError,
    score !== "" && (!/^\d+$/.test(score) || Number(score) > MAX_RISK_SCORE)
      ? `Risk score must be a whole number from 0 to ${MAX_RISK_SCORE}.` : "");
  if (!patientOk || !scoreOk) {
    return null;
  }

  if (patient !== "") {
    filters.patient_nbr = patient;
  }
  if (score !== "") {
    filters.risk_score = score;
  }
  if (searchLevelSelect.value !== "") {
    filters.risk_level = searchLevelSelect.value;
  }
  return filters;
}

// Highlight the chip that matches the Risk Level dropdown
function syncChips() {
  for (const chip of chips) {
    chip.setAttribute("aria-pressed", String(chip.dataset.level === searchLevelSelect.value));
  }
}

function badge(text, className) {
  const span = document.createElement("span");
  span.className = `badge ${className}`;
  span.textContent = text;
  return span;
}

function textCell(text) {
  const cell = document.createElement("td");
  cell.textContent = text === null || text === undefined ? "-" : String(text);
  return cell;
}

function badgeCell(value, className) {
  const cell = document.createElement("td");
  if (value) {
    cell.appendChild(badge(value.replaceAll("_", " "), className));
  }
  else {
    cell.textContent = "-";
  }
  return cell;
}

// One table row per encounter. textContent (not innerHTML) so stored text can never run as HTML.
function resultRow(row) {
  const tr = document.createElement("tr");
  // The encounter ID opens the Care Intervention tab for that encounter (openCareFor is in care.js)
  const idCell = document.createElement("td");
  const idLink = document.createElement("button");
  idLink.type = "button";
  idLink.className = "link-button";
  idLink.textContent = `#${row.encounter_id}`;
  idLink.title = "Open in Care Intervention";
  idLink.addEventListener("click", () => openCareFor(row.encounter_id));
  idCell.appendChild(idLink);
  tr.appendChild(idCell);
  tr.appendChild(textCell(`#${row.patient_nbr}`));
  tr.appendChild(textCell(row.age));
  tr.appendChild(textCell(row.time_in_hospital === null ? null : `${row.time_in_hospital} days`));
  const prior = [row.number_inpatient, row.number_emergency, row.number_outpatient].map((n) => n ?? "-");
  tr.appendChild(textCell(prior.join(" / ")));
  tr.appendChild(textCell(row.num_medications));

  const scoreCell = document.createElement("td");
  const score = document.createElement("strong");
  score.textContent = row.risk_score;
  scoreCell.append(score, ` / ${MAX_RISK_SCORE}`);
  tr.appendChild(scoreCell);

  tr.appendChild(badgeCell(row.risk_level, `risk-${row.risk_level.toLowerCase()}`));
  tr.appendChild(textCell(row.readmitted));
  tr.appendChild(badgeCell(row.intervention_status, "status"));
  tr.appendChild(textCell(row.assigned_to));
  return tr;
}

function showResultsMessage(text, isError) {
  resultsBody.replaceChildren();
  const tr = document.createElement("tr");
  const td = document.createElement("td");
  td.colSpan = 11;
  td.textContent = text;
  td.className = isError ? "error-cell" : "";
  tr.appendChild(td);
  resultsBody.appendChild(tr);
}

function updatePager(rowCount) {
  prevPageButton.disabled = currentOffset === 0;
  // A full page means there may be more; the API does not return a total count
  nextPageButton.disabled = rowCount < PAGE_SIZE;
  pageInfo.textContent = rowCount === 0 ? "" : `Rows ${currentOffset + 1}-${currentOffset + rowCount}`;
}

async function runSearch(filters, offset) {
  const requestId = ++searchRequestId;
  currentFilters = filters;
  currentOffset = offset;
  searchLoaded = true;
  searchButton.disabled = true;
  resultsSummary.textContent = "Searching...";

  const params = new URLSearchParams({ ...filters, limit: PAGE_SIZE, offset: offset });
  try {
    const response = await fetch(`${SEARCH_URL}?${params}`);
    const body = await response.json();
    if (requestId !== searchRequestId) {
      return;  // a newer search started while this one was loading
    }
    if (!response.ok) {
      throw new Error(describeError(response.status, body));
    }
    if (body.length === 0) {
      showResultsMessage(offset === 0 ? "No encounters match these filters." : "No more results.", false);
    }
    else {
      resultsBody.replaceChildren(...body.map(resultRow));
    }
    resultsSummary.textContent = `Showing ${body.length} encounter(s) (HIGH risk prioritized)`;
    updatePager(body.length);
  }
  catch (error) {
    if (requestId !== searchRequestId) {
      return;
    }
    // fetch itself throws a TypeError when the server is down or CORS blocks the response
    const text = error instanceof TypeError
      ? "Could not reach the API. Is the backend running, and is this page opened from http://127.0.0.1:5173?"
      : error.message;
    resultsSummary.textContent = "Search failed";
    showResultsMessage(text, true);
    updatePager(0);
  }
  finally {
    if (requestId === searchRequestId) {
      searchButton.disabled = false;
    }
  }
}

function searchFromForm() {
  const filters = readSearchFilters();
  if (filters === null) {
    return;
  }
  syncChips();
  runSearch(filters, 0);
}

// Called by tabs.js the first time the Search tab is opened, so the table is not empty
function ensureSearchLoaded() {
  if (!searchLoaded) {
    searchFromForm();
  }
}

searchForm.addEventListener("submit", function (event) {
  event.preventDefault();
  searchFromForm();
});

document.getElementById("reset-filters-btn").addEventListener("click", function () {
  searchForm.reset();
  setFieldError(searchPatientInput, searchPatientError, "");
  setFieldError(searchScoreInput, searchScoreError, "");
  searchFromForm();
});

for (const chip of chips) {
  chip.addEventListener("click", function () {
    searchLevelSelect.value = chip.dataset.level;
    searchFromForm();
  });
}

searchLevelSelect.addEventListener("change", syncChips);
document.getElementById("refresh-btn").addEventListener("click", () => runSearch(currentFilters, currentOffset));
prevPageButton.addEventListener("click", () => runSearch(currentFilters, Math.max(0, currentOffset - PAGE_SIZE)));
nextPageButton.addEventListener("click", () => runSearch(currentFilters, currentOffset + PAGE_SIZE));
