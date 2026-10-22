"""Clean raw CSV rows to match the patient_encounters column types.
INTEGER/BIGINT columns become int (missing -> 0); VARCHAR columns stay str (missing -> None)."""

INT_COLUMNS = [
    "encounter_id",
    "patient_nbr",
    "time_in_hospital",
    "number_inpatient",
    "number_emergency",
    "number_outpatient",
    "num_medications",
    "num_lab_procedures",
    "num_procedures",
    "admission_type_id",
    "discharge_disposition_id",
]
TEXT_COLUMNS = ["age", "readmitted"]

# Raw values treated as missing ('?' is the dataset's own marker).
NULL_VALUES = {"", "?", "none", "null", "nan", "n/a"}


def is_null(value) -> bool:
    return value is None or str(value).strip().lower() in NULL_VALUES


def to_int(value) -> int:
    """Convert to int; None/null-like values become 0."""
    if is_null(value):
        return 0
    return int(float(str(value).strip()))


def to_text(value) -> str | None:
    """Keep as a stripped string; None/null-like values become None."""
    return None if is_null(value) else str(value).strip()


def clean_row(raw: dict) -> dict:
    row = {c: to_int(raw.get(c)) for c in INT_COLUMNS}
    row.update({c: to_text(raw.get(c)) for c in TEXT_COLUMNS})
    return row


KEY_COLUMNS = ["encounter_id", "patient_nbr"]


def key_problem(row: dict) -> str | None:
    """Return the reason a cleaned row can't be loaded, or None if its keys are valid."""
    for c in KEY_COLUMNS:
        if row[c] <= 0:
            return f"missing or invalid {c}"
    return None


def check_types(row: dict) -> None:
    """Raise TypeError if any value doesn't match its schema column type."""
    bad = {}
    for c in INT_COLUMNS:
        if not isinstance(row[c], int):
            bad[c] = (type(row[c]).__name__, "int")
    for c in TEXT_COLUMNS:
        if row[c] is not None and not isinstance(row[c], str):
            bad[c] = (type(row[c]).__name__, "str")
    if bad:
        raise TypeError(f"Type mismatch (got, expected): {bad}")
