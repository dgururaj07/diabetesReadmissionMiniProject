from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class HealthResponse(BaseModel):
    status: str


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Readmitted(str, Enum):
    WITHIN_30_DAYS = "<30"
    AFTER_30_DAYS = ">30"
    NO = "NO"


class InterventionStatus(str, Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    ASSIGNED = "ASSIGNED"
    CONTACTED = "CONTACTED"
    FOLLOW_UP_SCHEDULED = "FOLLOW_UP_SCHEDULED"
    CLOSED = "CLOSED"


class InterventionUpdate(BaseModel):
    status: Optional[InterventionStatus] = None
    assigned_to: Optional[str] = Field(default=None, max_length=100)
    notes: Optional[str] = None

    @model_validator(mode="after")
    def require_one_field(self):
        if self.status is None and self.assigned_to is None and self.notes is None:
            raise ValueError("Provide at least one of: status, assigned_to, notes")
        return self


# alias -> canonical field name, accepted on POST /encounters
ENCOUNTER_ALIASES = {
    "patient_number": "patient_nbr",
    "patient-number": "patient_nbr",
    "hospital": "time_in_hospital",
    "inpatient": "number_inpatient",
    "emergency": "number_emergency",
    "medications": "num_medications",
}


class EncounterCreate(BaseModel):
    # Optional so a missing or non-positive number gets the service's 400, not a 422
    patient_nbr: Optional[int] = None
    age: Optional[str] = Field(default=None, max_length=30)
    time_in_hospital: Optional[int] = Field(default=0, ge=0)
    number_inpatient: Optional[int] = Field(default=0, ge=0)
    number_emergency: Optional[int] = Field(default=0, ge=0)
    number_outpatient: Optional[int] = Field(default=0, ge=0)
    num_medications: Optional[int] = Field(default=0, ge=0)
    num_lab_procedures: Optional[int] = Field(default=0, ge=0)
    num_procedures: Optional[int] = Field(default=0, ge=0)
    admission_type_id: Optional[int] = 1
    discharge_disposition_id: Optional[int] = 1
    readmitted: Optional[Readmitted] = Readmitted.NO  # historical outcome: stored only, never scored

    @model_validator(mode="before")
    @classmethod
    def apply_aliases(cls, data):
        if isinstance(data, dict):
            data = dict(data)
            for alias, field in ENCOUNTER_ALIASES.items():
                if field not in data and alias in data:
                    data[field] = data[alias]
        return data


class EncounterResponse(BaseModel):
    encounter_id: int
    patient_nbr: int
    age: Optional[str] = None
    time_in_hospital: Optional[int] = None
    number_inpatient: Optional[int] = None
    number_emergency: Optional[int] = None
    number_outpatient: Optional[int] = None
    num_medications: Optional[int] = None
    num_lab_procedures: Optional[int] = None
    num_procedures: Optional[int] = None
    admission_type_id: Optional[int] = None
    discharge_disposition_id: Optional[int] = None
    readmitted: Optional[str] = None
    risk_score: int
    risk_level: RiskLevel
    review_reason: Optional[str] = None
    created_at: Optional[datetime] = None
    intervention_id: Optional[int] = None
    status: Optional[InterventionStatus] = None


class PatientSearchResult(BaseModel):
    """One encounter row from /patients/search, with its care intervention (null for LOW risk, which is not queued)."""
    encounter_id: int
    patient_nbr: int
    age: Optional[str] = None
    time_in_hospital: Optional[int] = None
    number_inpatient: Optional[int] = None
    number_emergency: Optional[int] = None
    number_outpatient: Optional[int] = None
    num_medications: Optional[int] = None
    num_lab_procedures: Optional[int] = None
    discharge_disposition_id: Optional[int] = None
    admission_type_id: Optional[int] = None
    readmitted: Optional[str] = None
    risk_score: int
    risk_level: RiskLevel
    review_reason: Optional[str] = None
    intervention_id: Optional[int] = None
    status: Optional[InterventionStatus] = None
    intervention_status: Optional[InterventionStatus] = None  # same as status, kept for frontend compatibility
    assigned_to: Optional[str] = None
    notes: Optional[str] = None


class OperationsSummary(BaseModel):
    total_encounters: int
    high_risk: int
    medium_risk: int
    low_risk: int
    pending_interventions: int
    assigned_interventions: int
    contacted_interventions: int
    follow_up_scheduled: int
    closed_interventions: int


class ReadmissionAnalysis(BaseModel):
    overall_encounters: int
    overall_readmitted_under_30_days: int
    overall_readmission_rate: float
    high_risk_patients: int
    high_risk_readmitted_under_30_days: int
    high_risk_readmission_rate: float
    medium_risk_patients: int
    medium_risk_readmitted_under_30_days: int
    medium_risk_readmission_rate: float
    low_risk_patients: int
    low_risk_readmitted_under_30_days: int
    low_risk_readmission_rate: float
    note: str


class ManagementDashboard(BaseModel):
    total_diabetes_encounters: int
    readmitted_under_30_days: int
    readmission_rate: float
    high_risk_population: int
    high_risk_percent: float
    high_risk_30_day_readmissions: int
    care_queue_pending: int
