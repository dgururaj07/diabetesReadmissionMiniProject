# Diabetes Readmission Intervention Queue

An educational prototype that helps a care team decide **which diabetes patients to follow up with first**.

Each hospital encounter gets a transparent, rule-based **risk score (0–8)** and a level of **LOW / MEDIUM / HIGH**.
MEDIUM and HIGH encounters go into a **care queue**, where staff assign a clinician, record notes and track
outreach until the case is closed.

> This is not a clinical tool. The scoring rules are simple heuristics for learning, not a validated model.

## How it fits together

```
diabetic_data.csv ──► ingestion scripts ──► PostgreSQL ◄── FastAPI (backend/) ◄── Browser UI (frontendAssignment/)
                      (clean, score,         patient_encounters                    Add / Search / Care Intervention
                       queue MEDIUM+HIGH)    care_interventions
```

| Folder | What it is |
|---|---|
| [backend/](backend/) | FastAPI REST API, PostgreSQL schema, CSV ingestion scripts and pytest suite. See [backend/README.md](backend/README.md). |
| [frontendAssignment/](frontendAssignment/) | Plain HTML/CSS/JavaScript UI with three tabs: add an encounter, search patients, update a care intervention. See [frontendAssignment/README.md](frontendAssignment/README.md). |
| [day5/](day5/) | Step-by-step TypeScript and HTML exercises calling the API (learning material). |
| [frontend/](frontend/) | Empty, reserved for a future React/Vite app. |
| [prompts/](prompts/) | Prompt notes used while building the endpoints. |
| [diabetes-readmission-api.postman_collection.json](diabetes-readmission-api.postman_collection.json) | Postman collection with a saved request for every endpoint. |

## Risk scoring

A rule adds its points when the encounter's value is at or above the threshold:

| Rule | Points |
|---|---|
| 3+ prior inpatient visits | 3 |
| 2+ emergency visits | 2 |
| 3+ outpatient visits | 1 |
| 7+ days in hospital | 1 |
| 20+ medications | 1 |

**HIGH** is 5 or more points, **MEDIUM** is 3–4, and **LOW** is 0–2. The `review_reason` lists the rules that fired.

The historical `readmitted` field is **never used for scoring**, because it is the outcome being predicted. It is
stored only so that the risk groups can be compared with real readmissions afterwards
(`/operations/readmission-analysis`).

## Quick start

You need **Python 3.13** and **PostgreSQL**. Run these from the repo root in PowerShell.

1. **Install the backend's packages** into a virtual environment:
   ```powershell
   python -m venv .venv
   .venv\Scripts\python.exe -m pip install -r backend\requirement.txt pytest httpx
   ```
2. **Set up the database:** create `backend/.env` and the tables, then load the CSV. See
   [backend/README.md](backend/README.md#setup) for the details.
3. **Start the API** on http://127.0.0.1:8000 (interactive docs at `/docs`):
   ```powershell
   cd backend
   ..\.venv\Scripts\uvicorn.exe api.main:app --reload
   ```
4. **Serve the UI** in a second terminal, from the repo root:
   ```powershell
   .venv\Scripts\python.exe -m http.server 5173 --bind 127.0.0.1 --directory frontendAssignment
   ```
5. **Open http://127.0.0.1:5173/index.html.** Use this address, not the file itself: a page opened from disk has
   origin `null`, which the API's CORS settings reject.

## Running the tests

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest -q
```

The tests run against your PostgreSQL in a temporary schema that is created and dropped for each test file, so
your real data is never read or changed. If PostgreSQL can't be reached, the database tests are skipped.
