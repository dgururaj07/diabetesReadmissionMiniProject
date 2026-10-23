"""Read + clean the first CSV row, calculate its risk, and insert it into patient_encounters.
Connection settings come from the PG* variables in the project's .env file."""
import os
from pathlib import Path

import psycopg

from read_first_row import read_first_row
from risk import calculate_risk

ROOT = Path(__file__).parent.parent

COLUMNS = [
    "encounter_id", "patient_nbr", "age", "time_in_hospital", "number_inpatient",
    "number_emergency", "number_outpatient", "num_medications", "num_lab_procedures",
    "num_procedures", "admission_type_id", "discharge_disposition_id", "readmitted",
    "risk_score", "risk_level", "review_reason",
]


def load_env(path: Path = ROOT / ".env") -> None:
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def connect() -> psycopg.Connection:
    load_env()
    # libpq reads PGHOST, PGPORT, PGDATABASE, PGUSER and PGPASSWORD from the environment.
    return psycopg.connect()


def insert_encounter(conn: psycopg.Connection, record: dict) -> bool:
    """Insert one record; return False if its encounter_id already exists."""
    sql = (
        f"INSERT INTO patient_encounters ({', '.join(COLUMNS)}) "
        f"VALUES ({', '.join('%s' for _ in COLUMNS)}) "
        "ON CONFLICT (encounter_id) DO NOTHING"
    )
    cur = conn.execute(sql, [record[c] for c in COLUMNS])
    return cur.rowcount == 1


if __name__ == "__main__":
    row = read_first_row()              # cleaned + type-checked
    record = row | calculate_risk(row)  # adds risk_score, risk_level, review_reason

    with connect() as conn:
        inserted = insert_encounter(conn, record)
        saved = conn.execute(
            "SELECT encounter_id, patient_nbr, risk_score, risk_level, review_reason, created_at "
            "FROM patient_encounters WHERE encounter_id = %s",
            [record["encounter_id"]],
        ).fetchone()

    print("Inserted new row" if inserted else "Row already existed, nothing inserted")
    print(saved)
