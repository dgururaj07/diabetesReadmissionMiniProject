"""Create a care_interventions row (status PENDING_REVIEW) for every HIGH or MEDIUM risk encounter.
Re-runnable: encounters that already have an intervention are skipped (encounter_id is UNIQUE)."""
from insert_first_row import connect

INSERT_SQL = """
INSERT INTO care_interventions (encounter_id, status)
SELECT encounter_id, 'PENDING_REVIEW'
FROM patient_encounters
WHERE risk_level IN ('HIGH', 'MEDIUM')
ON CONFLICT (encounter_id) DO NOTHING
"""


def load_interventions() -> None:
    with connect() as conn:  # commits on success, rolls back on any error
        eligible = conn.execute(
            "SELECT count(*) FROM patient_encounters WHERE risk_level IN ('HIGH', 'MEDIUM')"
        ).fetchone()[0]
        inserted = conn.execute(INSERT_SQL).rowcount
        total = conn.execute("SELECT count(*) FROM care_interventions").fetchone()[0]
        by_level = conn.execute(
            "SELECT e.risk_level, count(*) FROM care_interventions i "
            "JOIN patient_encounters e USING (encounter_id) GROUP BY e.risk_level"
        ).fetchall()

    print(f"HIGH/MEDIUM encounters: {eligible}; interventions inserted: {inserted}; "
          f"already present: {eligible - inserted}")
    print(f"care_interventions now holds {total} rows: {dict(by_level)}")


if __name__ == "__main__":
    load_interventions()
