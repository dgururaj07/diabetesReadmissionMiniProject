from api.db import fetch_all, fetch_one


def list_encounters(risk_level, readmitted, limit, offset):
    clauses, params = [], []
    if risk_level:
        clauses.append("risk_level = %s")
        params.append(risk_level)
    if readmitted:
        clauses.append("readmitted = %s")
        params.append(readmitted)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return fetch_all(
        f"SELECT * FROM patient_encounters {where} ORDER BY encounter_id LIMIT %s OFFSET %s",
        (*params, limit, offset),
    )


def get_encounter(encounter_id):
    return fetch_one(
        """
        SELECT e.*, ci.intervention_id, ci.status AS intervention_status, ci.assigned_to,
               ci.notes AS intervention_notes,
               ci.created_at AS intervention_created_at, ci.updated_at AS intervention_updated_at
        FROM patient_encounters e
        LEFT JOIN care_interventions ci ON ci.encounter_id = e.encounter_id
        WHERE e.encounter_id = %s
        """,
        (encounter_id,),
    )


QUEUE_SELECT = """
    SELECT e.encounter_id, e.patient_nbr, e.age, e.risk_score, e.risk_level, e.review_reason,
           ci.intervention_id, ci.status, ci.assigned_to, ci.notes, ci.created_at, ci.updated_at
    FROM care_interventions ci
    JOIN patient_encounters e ON e.encounter_id = ci.encounter_id
"""


def list_care_queue(risk_level, status, assigned_to, limit, offset):
    clauses, params = ["e.risk_level IN ('MEDIUM', 'HIGH')"], []
    if risk_level:
        clauses.append("e.risk_level = %s")
        params.append(risk_level)
    if status:
        clauses.append("ci.status = %s")
        params.append(status)
    if assigned_to:
        clauses.append("ci.assigned_to = %s")
        params.append(assigned_to)
    order = "ORDER BY CASE e.risk_level WHEN 'HIGH' THEN 0 ELSE 1 END, ci.created_at, ci.intervention_id"
    return fetch_all(
        f"{QUEUE_SELECT} WHERE {' AND '.join(clauses)} {order} LIMIT %s OFFSET %s",
        (*params, limit, offset),
    )
