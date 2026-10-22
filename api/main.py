from typing import Optional

import psycopg
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

from api import repository
from api.errors import NotFoundError
from api.models import HealthResponse, InterventionStatus, Readmitted, RiskLevel

app = FastAPI(title="Diabetes Readmission Intervention Queue")

LIMIT = Query(50, ge=1, le=500, description="Page size")
OFFSET = Query(0, ge=0, description="Rows to skip")


def _value(option):
    return option.value if option else None


@app.exception_handler(psycopg.OperationalError)
def database_unavailable(request, exc):
    return JSONResponse(status_code=503, content={"detail": "Database is unavailable. Try again later."})


@app.exception_handler(NotFoundError)
def not_found(request, exc):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.get("/health", response_model=HealthResponse, summary="Service health check")
def health():
    return {"status": "ok"}


@app.get("/encounters", summary="List diabetes encounters")
def list_encounters(risk_level: Optional[RiskLevel] = None, readmitted: Optional[Readmitted] = None,
                    limit: int = LIMIT, offset: int = OFFSET):
    return repository.list_encounters(_value(risk_level), _value(readmitted), limit, offset)


@app.get("/encounters/{encounter_id}", summary="Get one encounter with its intervention")
def get_encounter(encounter_id: int):
    encounter = repository.get_encounter(encounter_id)
    if encounter is None:
        raise NotFoundError(f"Encounter {encounter_id} not found")
    return encounter


@app.get("/care-queue", summary="View the MEDIUM + HIGH risk care queue")
def get_care_queue(risk_level: Optional[RiskLevel] = None, status: Optional[InterventionStatus] = None,
                   assigned_to: Optional[str] = None, limit: int = LIMIT, offset: int = OFFSET):
    return repository.list_care_queue(_value(risk_level), _value(status), assigned_to, limit, offset)
