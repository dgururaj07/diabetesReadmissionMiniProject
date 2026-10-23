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
