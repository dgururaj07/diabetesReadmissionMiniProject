"""Rule-based risk scoring for patient_encounters.
`readmitted` is a historical outcome and is never used for scoring."""

# (field, threshold, points, reason)
RISK_RULES = (
    ("number_inpatient", 3, 3, "3+ prior inpatient visits"),
    ("number_emergency", 2, 2, "2+ emergency visits"),
    ("number_outpatient", 3, 1, "3+ outpatient visits"),
    ("time_in_hospital", 7, 1, "7+ days in hospital"),
    ("num_medications", 20, 1, "20+ medications"),
)


def calculate_risk(encounter: dict) -> dict:
    score, reasons = 0, []
    for field, threshold, points, reason in RISK_RULES:
        if (encounter.get(field) or 0) >= threshold:
            score += points
            reasons.append(reason)
    level = "HIGH" if score >= 5 else "MEDIUM" if score >= 3 else "LOW"
    return {
        "risk_score": score,
        "risk_level": level,
        "review_reason": "; ".join(reasons) or "No prioritization rules triggered",
    }
