from api import repository
from api.errors import InvalidInputError
from ingestion.risk import RISK_RULES, calculate_risk

COUNT_FIELDS = ("time_in_hospital", "number_inpatient", "number_emergency", "number_outpatient",
                "num_medications", "num_lab_procedures", "num_procedures")

MAX_RISK_SCORE = sum(points for _, _, points, _ in RISK_RULES)  # highest possible score, currently 8
RISK_LEVELS = ("LOW", "MEDIUM", "HIGH")


def normalize_search(patient_nbr=None, risk_score=None, risk_level=None, limit=50, offset=0) -> dict:
    """Validate /patients/search filters. Repeats the route checks so it is safe outside HTTP too."""
    if patient_nbr is not None and patient_nbr <= 0:
        raise InvalidInputError("Patient Number must be a positive integer.")
    if risk_score is not None and not 0 <= risk_score <= MAX_RISK_SCORE:
        raise InvalidInputError(f"Risk score must be between 0 and {MAX_RISK_SCORE}.")
    level = None
    if risk_level is not None:
        level = risk_level.strip().upper()
        if level not in RISK_LEVELS:
            raise InvalidInputError(f"Invalid risk_level '{risk_level}'. Allowed: {', '.join(RISK_LEVELS)}.")
    return {"patient_nbr": patient_nbr, "risk_score": risk_score, "risk_level": level,
            "limit": min(max(limit, 1), 500), "offset": max(0, offset)}


def create_encounter(data: dict) -> dict:
    """Score a new encounter (never from `readmitted`), store it, and queue it when MEDIUM/HIGH."""
    patient_nbr = data.get("patient_nbr")
    if patient_nbr is None or patient_nbr <= 0:
        raise InvalidInputError("Patient Number must be a positive integer.")
    encounter = {
        "patient_nbr": patient_nbr,
        "age": data.get("age"),
        **{field: max(0, int(data.get(field) or 0)) for field in COUNT_FIELDS},
        "admission_type_id": int(data.get("admission_type_id") or 1),
        "discharge_disposition_id": int(data.get("discharge_disposition_id") or 1),
        "readmitted": data.get("readmitted") or "NO",
    }
    encounter.update(calculate_risk(encounter))
    created = repository.create_encounter(encounter)
    if created is None:
        raise InvalidInputError("Failed to create encounter")
    return created


def build_operations_summary(counts: dict, status_rows: list) -> dict:
    by_status = {row["status"]: row["count"] for row in status_rows}
    return {
        "total_encounters": counts["total_encounters"],
        "high_risk": counts["high_risk"],
        "medium_risk": counts["medium_risk"],
        "low_risk": counts["low_risk"],
        "pending_interventions": by_status.get("PENDING_REVIEW", 0),
        "assigned_interventions": by_status.get("ASSIGNED", 0),
        "contacted_interventions": by_status.get("CONTACTED", 0),
        "follow_up_scheduled": by_status.get("FOLLOW_UP_SCHEDULED", 0),
        "closed_interventions": by_status.get("CLOSED", 0),
    }


OUTCOME_NOTE = ("The historical readmitted field is used only for retrospective validation "
                "and is not used in risk scoring.")


def percentage(part: int, whole: int) -> float:
    return round(part * 100 / whole, 2) if whole else 0.0


def _group_totals(group_rows: list) -> dict:
    totals = {level: (0, 0) for level in ("HIGH", "MEDIUM", "LOW")}
    for row in group_rows:
        totals[row["risk_level"]] = (row["encounters"], row["readmitted_under_30"])
    return totals


def build_readmission_analysis(group_rows: list) -> dict:
    """Compare already-assigned risk groups with the historical <30 outcome.

    Rates differing does not prove the rules are predictive."""
    totals = _group_totals(group_rows)
    all_count = sum(count for count, _ in totals.values())
    all_readmitted = sum(readmitted for _, readmitted in totals.values())
    result = {"overall_encounters": all_count, "overall_readmitted_under_30_days": all_readmitted,
              "overall_readmission_rate": percentage(all_readmitted, all_count)}
    for level, (count, readmitted) in totals.items():
        prefix = f"{level.lower()}_risk"
        result[f"{prefix}_patients"] = count
        result[f"{prefix}_readmitted_under_30_days"] = readmitted
        result[f"{prefix}_readmission_rate"] = percentage(readmitted, count)
    result["note"] = OUTCOME_NOTE
    return result


def build_management_dashboard(group_rows: list, pending: int) -> dict:
    totals = _group_totals(group_rows)
    all_count = sum(count for count, _ in totals.values())
    all_readmitted = sum(readmitted for _, readmitted in totals.values())
    high_count, high_readmitted = totals["HIGH"]
    return {
        "total_diabetes_encounters": all_count,
        "readmitted_under_30_days": all_readmitted,
        "readmission_rate": percentage(all_readmitted, all_count),
        "high_risk_population": high_count,
        "high_risk_percent": percentage(high_count, all_count),  # population share, not a readmission rate
        "high_risk_30_day_readmissions": high_readmitted,
        "care_queue_pending": pending,
    }
