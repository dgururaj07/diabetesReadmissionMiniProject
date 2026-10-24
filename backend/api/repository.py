from api.db import connection, fetch_all, fetch_one


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


def update_intervention(encounter_id, status, assigned_to, notes):
    """Returns the updated row, or None when the encounter has no intervention. Fields left as None are kept."""
    return fetch_one(
        """
        UPDATE care_interventions
        SET status = COALESCE(%s, status), assigned_to = COALESCE(%s, assigned_to),
            notes = COALESCE(%s, notes), updated_at = CURRENT_TIMESTAMP
        WHERE encounter_id = %s
        RETURNING intervention_id, encounter_id, status, assigned_to, notes, created_at, updated_at
        """,
        (status, assigned_to, notes, encounter_id),
    )


def get_risk_counts():
    return fetch_one(
        """
        SELECT COUNT(*) AS total_encounters,
               COUNT(*) FILTER (WHERE risk_level = 'HIGH') AS high_risk,
               COUNT(*) FILTER (WHERE risk_level = 'MEDIUM') AS medium_risk,
               COUNT(*) FILTER (WHERE risk_level = 'LOW') AS low_risk
        FROM patient_encounters
        """
    )


def get_status_counts():
    return fetch_all("SELECT status, COUNT(*) AS count FROM care_interventions GROUP BY status")


def get_risk_group_outcomes():
    """Per risk group: encounter count and historical <30 readmissions.

    `readmitted` is used here only AFTER scoring, for retrospective validation."""
    return fetch_all(
        """
        SELECT risk_level, COUNT(*) AS encounters,
               COUNT(*) FILTER (WHERE readmitted = '<30') AS readmitted_under_30
        FROM patient_encounters
        GROUP BY risk_level
        """
    )


def count_pending_interventions():
    return fetch_one("SELECT COUNT(*) AS count FROM care_interventions WHERE status = 'PENDING_REVIEW'")["count"]


ENCOUNTER_COLUMNS = ("patient_nbr", "age", "time_in_hospital", "number_inpatient", "number_emergency",
                     "number_outpatient", "num_medications", "num_lab_procedures", "num_procedures",
                     "admission_type_id", "discharge_disposition_id", "readmitted",
                     "risk_score", "risk_level", "review_reason")


def create_encounter(encounter):
    """Insert the encounter and, for MEDIUM/HIGH, its PENDING_REVIEW intervention in one transaction.

    encounter_id has no sequence, so MAX + 1 is used; the table lock makes concurrent creates wait their turn
    instead of colliding on the same id (plain reads are not blocked)."""
    columns = ", ".join(ENCOUNTER_COLUMNS)
    placeholders = ", ".join(["%s"] * len(ENCOUNTER_COLUMNS))
    with connection() as conn:
        conn.execute("LOCK TABLE patient_encounters IN SHARE ROW EXCLUSIVE MODE")
        row = conn.execute(
            f"""
            WITH next_id AS (SELECT COALESCE(MAX(encounter_id), 0) + 1 AS encounter_id FROM patient_encounters)
            INSERT INTO patient_encounters (encounter_id, {columns}, created_at)
            SELECT next_id.encounter_id, {placeholders}, CURRENT_TIMESTAMP FROM next_id
            RETURNING *
            """,
            tuple(encounter[column] for column in ENCOUNTER_COLUMNS),
        ).fetchone()
        if row is None:
            return None
        intervention = {"intervention_id": None, "status": None}  # LOW risk is never queued
        if row["risk_level"] in ("MEDIUM", "HIGH"):
            intervention = conn.execute(
                """
                INSERT INTO care_interventions (encounter_id, status) VALUES (%s, 'PENDING_REVIEW')
                ON CONFLICT (encounter_id) DO UPDATE SET encounter_id = EXCLUDED.encounter_id
                RETURNING intervention_id, status
                """,
                (row["encounter_id"],),
            ).fetchone()
        return {**row, **intervention}


def search_patients(patient_nbr, risk_score, risk_level, limit, offset):
    """LEFT JOIN so LOW-risk encounters (no intervention) are returned too, with null intervention fields."""
    clauses, params = [], []
    for column, value in (("e.patient_nbr", patient_nbr), ("e.risk_score", risk_score), ("e.risk_level", risk_level)):
        if value is not None:
            clauses.append(f"{column} = %s")
            params.append(value)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return fetch_all(
        f"""
        SELECT e.encounter_id, e.patient_nbr, e.age, e.time_in_hospital, e.number_inpatient, e.number_emergency,
               e.number_outpatient, e.num_medications, e.num_lab_procedures, e.discharge_disposition_id,
               e.admission_type_id, e.readmitted, e.risk_score, e.risk_level, e.review_reason,
               ci.intervention_id, ci.status, ci.status AS intervention_status, ci.assigned_to, ci.notes
        FROM patient_encounters e
        LEFT JOIN care_interventions ci ON ci.encounter_id = e.encounter_id
        {where}
        ORDER BY CASE e.risk_level WHEN 'HIGH' THEN 0 WHEN 'MEDIUM' THEN 1 ELSE 2 END, e.risk_score DESC, e.encounter_id
        LIMIT %s OFFSET %s
        """,
        (*params, limit, offset),
    )
