Implement `GET /encounters` in this FastAPI + PostgreSQL project from scratch. First read the project layout (entry file, where models, config and database code live, test setup, import style) and follow its conventions: naming, import style, comment density. Reuse any existing database connection helper, config, and error classes. Change only what this task needs.

## Data this endpoint reads

A table `patient_encounters` (create it only if it does not exist, and only if I confirm; otherwise use the existing one). Columns used:
- encounter_id BIGINT PRIMARY KEY
- patient_nbr BIGINT NOT NULL
- age VARCHAR(30), time_in_hospital, number_inpatient, number_emergency, number_outpatient, num_medications, num_lab_procedures, num_procedures, admission_type_id, discharge_disposition_id (all INTEGER, nullable)
- readmitted VARCHAR(10)  -- historical outcome: values "<30", ">30", "NO"
- risk_score INTEGER NOT NULL
- risk_level VARCHAR(20) NOT NULL  -- CHECK IN ('LOW','MEDIUM','HIGH')
- review_reason TEXT
- created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
Indexes on risk_level and readmitted.

## Behaviour

`GET /encounters` returns a filtered, paged list of rows as a plain JSON list.

Query parameters (all optional):
| Name | Type | Default | Rules |
|---|---|---|---|
| risk_level | enum: LOW, MEDIUM, HIGH | none | exact match |
| readmitted | enum: "<30", ">30", "NO" | none | exact match |
| limit | int | 50 | minimum 1, maximum 500 |
| offset | int | 0 | minimum 0 |

Rules:
1. Filters combine with AND. A filter that is not supplied adds no condition.
2. Order by encounter_id ascending, so pages are stable and never overlap.
3. Return all columns (SELECT *). No response_model, no total count.
4. An empty result is an empty list with HTTP 200, not an error.

## Implementation, in layers

1. Enums (models module): `RiskLevel(str, Enum)` and `Readmitted(str, Enum)` with the values above.
2. Paging constants (entry file):

       LIMIT = Query(50, ge=1, le=500, description="Page size")
       OFFSET = Query(0, ge=0, description="Rows to skip")

3. Small helper to turn an optional enum into a plain string:

       def _value(option): return option.value if option else None

4. Route (entry file):

       @app.get("/encounters", summary="List diabetes encounters")
       def list_encounters(risk_level: Optional[RiskLevel] = None, readmitted: Optional[Readmitted] = None,
                           limit: int = LIMIT, offset: int = OFFSET):
           return repository.list_encounters(_value(risk_level), _value(readmitted), limit, offset)

5. Data-access function (repository module, the only place with SQL):

       def list_encounters(risk_level, readmitted, limit, offset):
           clauses, params = [], []
           if risk_level: clauses.append("risk_level = %s"); params.append(risk_level)
           if readmitted: clauses.append("readmitted = %s"); params.append(readmitted)
           where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
           return fetch_all(f"SELECT * FROM patient_encounters {where} ORDER BY encounter_id LIMIT %s OFFSET %s",
                            (*params, limit, offset))

   Adapt `fetch_all` and the placeholder style to the project's driver. Rows should come back as dicts (for psycopg 3, `row_factory=dict_row`) so FastAPI can serialize them.

## Hard requirements

- Every request-supplied value, including limit and offset, goes in as a bound parameter. Only fixed fragments such as `risk_level = %s` are joined into the SQL text. No string interpolation of request values.
- Validation happens at the API layer: invalid enum values or out-of-range paging return 422 from FastAPI. Not in SQL.
- If the database is unreachable, return a clean 503 `{"detail": "Database is unavailable. Try again later."}` through an exception handler, not a raw traceback. Reuse the project's existing error handling if it has some.
- `readmitted` is a historical outcome used only for filtering and analysis. It must never be used to compute risk_score or risk_level.

## Tests

Match the project's test style. Cover:
- no filters: rows ordered by encounter_id, at most 50
- each filter alone, and both together (AND)
- limit and offset: consecutive pages do not overlap
- 422 for risk_level=URGENT, limit=0, limit=501, offset=-1
- a filter that matches nothing returns []
Use a test database or fixtures. Do not run tests against my real data, and do not insert, update, or delete anything outside the test setup.

## Constraints

- Do not change other endpoints, the schema of existing tables, or any import process.
- Do not add dependencies beyond what the project already uses, except test-only ones, which you should flag.
- If anything here conflicts with the existing project (column names, response shape, paging scheme, import style), tell me what you chose and why.

## Before you finish

Run the new tests and the existing suite and report the results. If you could not run something, say so. Mention (but do not build) two follow-ups: a total-count field for clients that need page counts, and that `readmitted` has only 3 distinct values so its index has little benefit.
