# Backend: Diabetes Readmission Intervention API

FastAPI + Pydantic v2 REST API over PostgreSQL (psycopg 3). It scores diabetes encounters for readmission risk,
keeps a care queue of MEDIUM and HIGH risk encounters, and reports on queue workload and outcomes.

## Layout

```
backend/
├── api/
│   ├── main.py         Routes, CORS, and the error handlers (exceptions → HTTP status codes)
│   ├── service.py      Business rules and validation: no SQL, no HTTP
│   ├── repository.py   SQL only, parameterised queries
│   ├── models.py       Pydantic request/response models and enums
│   ├── db.py           Connections; reads backend/.env
│   └── errors.py       AppError, NotFoundError (404), InvalidInputError (400)
├── ingestion/          Load data/diabetic_data.csv into the database
│   ├── risk.py         Risk rules and calculate_risk(), shared by ingestion and the API
│   ├── clean_rows.py   Type cleaning and validation of CSV rows
│   ├── read_first_row.py, insert_first_row.py   Single-row walkthrough
│   ├── load_all_rows.py        Bulk load of every valid row
│   └── load_interventions.py   Queue every MEDIUM/HIGH encounter as PENDING_REVIEW
├── sql/
│   ├── 01_create_schema.sql              Tables, constraints, indexes
│   ├── 02_seed_intervention_statuses.sql Allowed intervention statuses
│   └── 03_reset.sql                      Empties both data tables (keeps the schema)
├── data/diabetic_data.csv   ~101,766 encounters (UCI "Diabetes 130-US hospitals" dataset)
├── tests/               pytest suite
├── pytest.ini
└── requirement.txt
```

Requests flow in one direction: `main.py` → `service.py` → `repository.py` → `db.py`. Errors are raised as
exceptions and turned into HTTP responses by handlers in `main.py`.

## Setup

1. **Install the packages** (from the repo root). `requirement.txt` lists the runtime packages only; pytest and
   httpx are needed for the tests.
   ```powershell
   python -m venv .venv
   .venv\Scripts\python.exe -m pip install -r backend\requirement.txt pytest httpx
   ```

2. **Create `backend/.env`** with your PostgreSQL connection. It's gitignored; never commit it.
   ```
   PGHOST=localhost
   PGPORT=5432
   PGDATABASE=fde_db
   PGUSER=fde_user
   PGPASSWORD=your-password
   ```
   libpq reads these variables directly. Variables already set in your environment take priority over the file.

3. **Create the tables and the status list**:
   ```powershell
   psql -d fde_db -U fde_user -f backend\sql\01_create_schema.sql
   psql -d fde_db -U fde_user -f backend\sql\02_seed_intervention_statuses.sql
   ```

4. **Load the data:** run the scripts from inside `ingestion/`, because they import each other by file name.
   ```powershell
   cd backend\ingestion
   ..\..\.venv\Scripts\python.exe load_all_rows.py        # clean, score and insert every valid CSV row
   ..\..\.venv\Scripts\python.exe load_interventions.py   # queue MEDIUM/HIGH encounters as PENDING_REVIEW
   ```
   Both scripts can be re-run safely: rows already loaded are skipped. Rows that fail cleaning are written to
   `ingestion/rejected_rows.csv`, and the load stops if more than 1% of rows are rejected. To start over, run
   `sql/03_reset.sql`.

5. **Start the API**:
   ```powershell
   cd backend
   ..\.venv\Scripts\uvicorn.exe api.main:app --reload
   ```
   It runs at http://127.0.0.1:8000. Interactive docs are at http://127.0.0.1:8000/docs.

## Database

| Table | Purpose |
|---|---|
| `patient_encounters` | One row per encounter, with its inputs, `risk_score`, `risk_level`, `review_reason` and the historical `readmitted` outcome |
| `care_interventions` | At most one per encounter (`encounter_id` is UNIQUE). Holds `status`, `assigned_to`, `notes` and timestamps. Only MEDIUM/HIGH encounters get one. |
| `intervention_statuses` | Allowed statuses: `PENDING_REVIEW` → `ASSIGNED` → `CONTACTED` → `FOLLOW_UP_SCHEDULED` → `CLOSED` |

## Endpoints

| Method & path | What it does |
|---|---|
| `GET /health` | Health check: `{"status": "ok"}` |
| `GET /encounters` | List encounters ordered by ID. Filters: `risk_level`, `readmitted`, `limit`, `offset` |
| `POST /encounters` | Add an encounter. The server scores it and, if MEDIUM/HIGH, queues it as `PENDING_REVIEW`. Returns **201**. |
| `GET /encounters/{encounter_id}` | One encounter with its intervention fields (null when it has none) |
| `GET /patients/search` | Search by `patient_nbr`, `risk_score` and/or `risk_level` (combined with AND). HIGH first, then score descending. |
| `GET /care-queue` | MEDIUM + HIGH queue, HIGH first, oldest first. Filters: `risk_level`, `status`, `assigned_to` |
| `GET /care-queue/high` | HIGH-risk queue only |
| `PATCH /interventions/{encounter_id}` | Update `status`, `assigned_to` and/or `notes`. A field that is left out or null keeps its old value. |
| `GET /operations/summary` | Counts by risk level and by intervention status |
| `GET /operations/readmission-analysis` | Compares each risk group with historical <30-day readmission rates |
| `GET /management/dashboard` | Headline metrics for management |

The list endpoints page with `limit` (1–500, default 50) and `offset` (default 0).

### Adding an encounter: `POST /encounters`

```bash
curl -X POST http://127.0.0.1:8000/encounters \
  -H "Content-Type: application/json" \
  -d '{"patient_nbr": 88888, "age": "[60-70)", "time_in_hospital": 8, "number_inpatient": 3,
       "number_emergency": 2, "num_medications": 22}'
```

This example returns `risk_score` 7, `HIGH`, `status: "PENDING_REVIEW"`.

- **Required:** only `patient_nbr` (> 0).
- **Defaults:** the count fields default to 0, `admission_type_id` and `discharge_disposition_id` to 1, and
  `readmitted` to `"NO"`.
- **Alias names:** `patient_number` or `patient-number`, `hospital`, `inpatient`, `emergency`, `medications`. If a
  request sends both forms, the canonical name wins.
- **Saved together:** the encounter and its intervention are written in one transaction, so an encounter is never
  saved without its queue entry.

### Searching: `GET /patients/search`

```bash
curl "http://127.0.0.1:8000/patients/search?patient_nbr=88888&risk_level=HIGH&limit=10"
```

No matches returns `[]`, never a 404. LOW-risk rows come back with all intervention fields null.

### Errors

| Status | When | Body |
|---|---|---|
| 400 | Business-rule failure, e.g. `patient_nbr` ≤ 0 | `{"detail": "Patient Number must be a positive integer."}` |
| 404 | Unknown encounter, or a PATCH to an encounter with no intervention | `{"detail": "Encounter 5 not found"}` |
| 422 | Request validation, e.g. bad enum value, negative count, `limit` > 500 | FastAPI's field-error list |
| 503 | PostgreSQL unreachable | `{"detail": "Database is unavailable. Try again later."}` |

### CORS

Only the origins in `ALLOWED_ORIGINS` (`api/main.py`) can read responses from a browser:
`http://localhost:5173` and `http://127.0.0.1:5173`. Serve the UI on port 5173, or add your origin to that list.
Never add `"null"` (pages opened from disk) or `"*"`.

## Tests

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest -q
```

| File | Covers |
|---|---|
| `test_health.py` | `/health` |
| `test_cors.py` | Allowed and blocked origins, preflight requests |
| `test_encounters.py` | Listing, detail, care queues, PATCH, 503 handling |
| `test_create_encounter.py` | `POST /encounters`: scoring, queueing, aliases, `readmitted` never scored, 400/422/503 |
| `test_search_patients.py` | `normalize_search`, route validation, real-SQL ordering, filters and paging |

The database tests build a temporary schema (`test_xxxxxxxx`) from `sql/01` and `sql/02`, point the API at it with
`PGOPTIONS`, and drop it afterwards, so your real tables are untouched. If PostgreSQL is unreachable they are
skipped, while the tests that fake the repository still run. The 503 tests point `PGPORT` at port 1 to simulate
an outage.

## Postman

`../diabetes-readmission-api.postman_collection.json` has a saved request for every endpoint. The `baseUrl`
collection variable defaults to `http://127.0.0.1:8000`. The POST and PATCH requests change real data.
