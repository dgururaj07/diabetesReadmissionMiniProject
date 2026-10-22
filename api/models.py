from enum import Enum

from pydantic import BaseModel


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
