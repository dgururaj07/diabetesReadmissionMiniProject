"""Read the first data row of data/diabetic_data.csv,
keeping only the columns defined in sql/01_create_schema.sql (patient_encounters)."""
import csv
from collections import Counter
from pathlib import Path

from clean_rows import INT_COLUMNS, TEXT_COLUMNS, check_types, clean_row, key_problem
from risk import calculate_risk

CSV_PATH = Path(__file__).parent.parent / "data" / "diabetic_data.csv"
REJECTS_PATH = Path(__file__).parent / "rejected_rows.csv"
MAX_REJECT_RATE = 0.01


def read_rows(path: Path = CSV_PATH, rejects: list | None = None):
    """Yield every valid CSV row, cleaned, as a dict of the patient_encounters source columns.

    Rows with a missing/invalid key, a non-numeric integer or a repeated encounter_id are
    skipped and appended to `rejects` as {"line": <csv line number>, "reason": ..., "row": ...}.
    """
    if rejects is None:
        rejects = []
    seen = set()
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = [c for c in INT_COLUMNS + TEXT_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path.name} is missing columns: {missing}")
        for raw in reader:
            line = reader.line_num
            try:
                result = clean_row(raw)
            except ValueError as e:
                rejects.append({"line": line, "reason": f"non-numeric value ({e})", "row": raw})
                continue
            reason = key_problem(result)
            if reason is None and result["encounter_id"] in seen:
                reason = "duplicate encounter_id"
            if reason:
                rejects.append({"line": line, "reason": reason, "row": raw})
                continue
            seen.add(result["encounter_id"])
            check_types(result)
            yield result


def write_rejects(rejects: list, path: Path = REJECTS_PATH) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["line", "reason", "encounter_id", "patient_nbr"])
        for r in rejects:
            writer.writerow([r["line"], r["reason"], r["row"].get("encounter_id"), r["row"].get("patient_nbr")])


def check_reject_rate(rejected: int, total: int) -> None:
    """Fail loudly if too many rows were rejected (likely a changed file format)."""
    if total and rejected / total > MAX_REJECT_RATE:
        raise RuntimeError(f"{rejected}/{total} rows rejected, over the {MAX_REJECT_RATE:.0%} limit")


def read_first_row(path: Path = CSV_PATH) -> dict:
    row = next(read_rows(path), None)
    if row is None:
        raise ValueError(f"{path.name} has no data rows")
    return row


def read_with_risk(path: Path = CSV_PATH, rejects: list | None = None):
    """Yield each valid row merged with its risk_score, risk_level and review_reason."""
    for row in read_rows(path, rejects):
        yield row | calculate_risk(row)


if __name__ == "__main__":
    first_row = read_first_row()
    for column, value in first_row.items():
        print(f"{column}: {value!r} ({type(value).__name__})")
    print(calculate_risk(first_row))

    rejects = []
    levels = Counter()
    for record in read_with_risk(rejects=rejects):
        levels[record["risk_level"]] += 1
    scored = sum(levels.values())
    print(f"Scored {scored} rows: {dict(levels)}")
    if rejects:
        write_rejects(rejects)
        print(f"Rejected {len(rejects)} rows -> {REJECTS_PATH}")
    check_reject_rate(len(rejects), scored + len(rejects))
