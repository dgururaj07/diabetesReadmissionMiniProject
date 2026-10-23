from typing import Optional

import psycopg
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api import repository, service
from api.errors import NotFoundError
from api.models import (HealthResponse, InterventionStatus, InterventionUpdate, ManagementDashboard, OperationsSummary,
                        ReadmissionAnalysis, Readmitted, RiskLevel)

app = FastAPI(title="Diabetes Readmission Intervention Queue")

# Browser origins allowed to read responses (the local Vite dev server). No credentials, no wildcard.
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


@app.get("/care-queue/high", summary="View the high-risk care queue")
def get_high_risk_queue(status: Optional[InterventionStatus] = None, assigned_to: Optional[str] = None,
                        limit: int = LIMIT, offset: int = OFFSET):
    return repository.list_care_queue("HIGH", _value(status), assigned_to, limit, offset)


@app.patch("/interventions/{encounter_id}", summary="Update care intervention")
def update_intervention(encounter_id: int, payload: InterventionUpdate):
    updated = repository.update_intervention(encounter_id, _value(payload.status), payload.assigned_to,
                                             payload.notes)
    if updated is None:
        if repository.get_encounter(encounter_id) is None:
            raise NotFoundError(f"Encounter {encounter_id} not found")
        raise NotFoundError(
            f"Encounter {encounter_id} has no care intervention (only MEDIUM/HIGH risk encounters are queued)")
    return updated


@app.get("/operations/summary", response_model=OperationsSummary, summary="Operational queue and workload metrics")
def operations_summary():
    return service.build_operations_summary(repository.get_risk_counts(), repository.get_status_counts())


@app.get("/operations/readmission-analysis", response_model=ReadmissionAnalysis,
         summary="Compare risk levels with historical readmission outcomes")
def readmission_analysis():
    """Compares risk groups (scored WITHOUT the outcome) with the historical `<30` readmission field.

    Retrospective validation only - differing rates do not prove the rules are clinically predictive."""
    return service.build_readmission_analysis(repository.get_risk_group_outcomes())


@app.get("/management/dashboard", response_model=ManagementDashboard, summary="Executive summary metrics")
def management_dashboard():
    return service.build_management_dashboard(repository.get_risk_group_outcomes(),
                                              repository.count_pending_interventions())
