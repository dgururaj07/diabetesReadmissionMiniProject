Add a health check endpoint to this FastAPI project from scratch. First read the project layout (entry file, where Pydantic models live, test setup, import style) and follow its conventions: naming, import style, and comment density. Change only what this task needs.

## Behaviour

`GET /health` returns HTTP 200 and exactly this JSON body:

    {"status": "ok"}

Rules:
1. It is a liveness check only. It must NOT touch the database, call external services, or read configuration, so it still responds when dependencies are down. A load balancer or monitor uses it to ask "is the process up?".
2. No authentication, no query parameters, no path parameters.
3. GET only.

## Implementation

1. Add a response model to the project's models module:

       class HealthResponse(BaseModel):
           status: str

2. Register the route in the app entry file:

       @app.get("/health", response_model=HealthResponse, summary="Service health check")
       def health(): return {"status": "ok"}

   Use a plain `def` (not async), since there is no I/O. Keep the one-line style only if the surrounding code uses it. Otherwise match the existing route style.
3. Do not add middleware, dependencies, or new packages for this.

## Test

Add a test in the project's test folder, matching its import style:

       from fastapi.testclient import TestClient
       from <your app module> import app

       def test_health():
           response = TestClient(app).get("/health")
           assert response.status_code == 200
           assert response.json() == {"status": "ok"}

TestClient needs `httpx`. If it is missing from the dev dependencies, tell me and add it there, not in runtime requirements.

## Constraints

- Do not add a database readiness check to /health. If I want one later, it will be a separate endpoint such as `/health/ready`. Mention that as a suggestion in your summary, but do not build it.
- Do not change other endpoints, models, or configuration.
- If /health already exists, show me the difference from this spec instead of overwriting it.

## Before you finish

Run the new test and the existing test suite, and report the results. Also run the app and confirm `GET /health` returns 200 with `{"status": "ok"}`. If anything could not be run, say so.
