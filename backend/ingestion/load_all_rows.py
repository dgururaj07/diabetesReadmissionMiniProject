"""Load every valid row of data/diabetic_data.csv into patient_encounters, with risk columns.
Re-runnable: encounter_ids already in the table are skipped. All-or-nothing: one transaction."""
from itertools import islice

from insert_first_row import COLUMNS, connect
from read_first_row import REJECTS_PATH, check_reject_rate, read_with_risk, write_rejects

BATCH_SIZE = 5000

INSERT_SQL = (
    f"INSERT INTO patient_encounters ({', '.join(COLUMNS)}) "
    f"VALUES ({', '.join('%s' for _ in COLUMNS)}) "
    "ON CONFLICT (encounter_id) DO NOTHING"
)


def batches(records, size=BATCH_SIZE):
    it = iter(records)
    while batch := list(islice(it, size)):
        yield batch


def load_all() -> None:
    rejects = []
    read = inserted = 0
    # Read and validate the whole file before touching the database.
    records = list(read_with_risk(rejects=rejects))
    read = len(records)
    if rejects:
        write_rejects(rejects)
        print(f"Rejected {len(rejects)} rows -> {REJECTS_PATH}")
    check_reject_rate(len(rejects), read + len(rejects))

    with connect() as conn:  # commits on success, rolls back on any error
        with conn.cursor() as cur:
            for batch in batches(records):
                cur.executemany(INSERT_SQL, [[r[c] for c in COLUMNS] for r in batch])
                inserted += cur.rowcount if cur.rowcount > 0 else 0
        total = conn.execute("SELECT count(*) FROM patient_encounters").fetchone()[0]
        levels = dict(conn.execute(
            "SELECT risk_level, count(*) FROM patient_encounters GROUP BY risk_level"
        ).fetchall())

    print(f"Read {read} valid rows; inserted {inserted}; already present {read - inserted}")
    print(f"patient_encounters now holds {total} rows: {levels}")


if __name__ == "__main__":
    load_all()
