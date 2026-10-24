import uuid
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from api import repository, service
from api.db import load_env
from api.errors import InvalidInputError
from api.main import app

SQL_DIR = Path(__file__).parent.parent / "sql"
SCHEMA_SQL = SQL_DIR / "01_create_schema.sql"
SEED_SQL = SQL_DIR / "02_seed_intervention_statuses.sql"

LOW_ROW = {"encounter_id": 9, "patient_nbr": 5, "age": None, "time_in_hospital": 1, "number_inpatient": 0,
           "number_emergency": 0, "number_outpatient": 0, "num_medications": 3, "num_lab_procedures": 10,
           "discharge_disposition_id": 1, "admission_type_id": 1, "readmitted": "NO", "risk_score": 0,
           "risk_level": "LOW", "review_reason": "No prioritization rules triggered", "intervention_id": None,
           "status": None, "intervention_status": None, "assigned_to": None, "notes": None}


@pytest.fixture
def fake_search(monkeypatch):
    """Replace the repository so route tests need no database; records the filters it was called with."""
    calls = []

    def search_patients(**filters):
        calls.append(filters)
        return []

    monkeypatch.setattr(repository, "search_patients", search_patients)
    return calls


# --- service: normalize_search

def test_normalize_defaults():
    assert service.normalize_search() == {"patient_nbr": None, "risk_score": None, "risk_level": None,
                                          "limit": 50, "offset": 0}


def test_normalize_cleans_level_and_clamps_paging():
    filters = service.normalize_search(risk_level=" high ", limit=9999, offset=-5)
    assert (filters["risk_level"], filters["limit"], filters["offset"]) == ("HIGH", 500, 0)


def test_normalize_raises_limit_below_one_to_one():
    assert service.normalize_search(limit=0)["limit"] == 1


def test_max_risk_score_comes_from_the_rules():
    assert service.MAX_RISK_SCORE == 8


@pytest.mark.parametrize("kwargs, message", [
    ({"patient_nbr": 0}, "Patient Number must be a positive integer."),
    ({"patient_nbr": -4}, "Patient Number must be a positive integer."),
    ({"risk_score": 9}, "Risk score must be between 0 and 8."),
    ({"risk_score": -1}, "Risk score must be between 0 and 8."),
    ({"risk_level": "EXTREME"}, "Invalid risk_level 'EXTREME'. Allowed: LOW, MEDIUM, HIGH."),
])
def test_normalize_rejects_invalid_input(kwargs, message):
    with pytest.raises(InvalidInputError) as error:
        service.normalize_search(**kwargs)
    assert str(error.value) == message


# --- route, with a fake repository

@pytest.mark.parametrize("params", [
    {"risk_score": 9}, {"risk_score": -1}, {"risk_level": "BAD"}, {"limit": 0}, {"limit": 501},
    {"offset": -1}, {"patient_nbr": "abc"}, {"risk_score": "x"},
])
def test_invalid_query_returns_422(fake_search, params):
    assert TestClient(app).get("/patients/search", params=params).status_code == 422
    assert fake_search == []


@pytest.mark.parametrize("patient_nbr", [0, -3])
def test_non_positive_patient_returns_400(fake_search, patient_nbr):
    response = TestClient(app).get("/patients/search", params={"patient_nbr": patient_nbr})
    assert response.status_code == 400
    assert response.json() == {"detail": "Patient Number must be a positive integer."}
    assert fake_search == []


def test_filters_are_passed_to_repository(fake_search):
    response = TestClient(app).get("/patients/search", params={"patient_nbr": 5, "risk_score": 3,
                                                               "risk_level": "MEDIUM", "limit": 10, "offset": 20})
    assert response.status_code == 200
    assert response.json() == []
    assert fake_search == [{"patient_nbr": 5, "risk_score": 3, "risk_level": "MEDIUM", "limit": 10, "offset": 20}]


def test_no_filters_uses_default_page(fake_search):
    assert TestClient(app).get("/patients/search").status_code == 200
    assert fake_search == [{"patient_nbr": None, "risk_score": None, "risk_level": None, "limit": 50, "offset": 0}]


def test_low_row_with_null_intervention_matches_response_model(monkeypatch):
    monkeypatch.setattr(repository, "search_patients", lambda **filters: [LOW_ROW])
    response = TestClient(app).get("/patients/search", params={"risk_level": "LOW"})
    assert response.status_code == 200
    assert response.json() == [LOW_ROW]


def test_search_database_down_returns_503(monkeypatch):
    load_env()
    monkeypatch.setenv("PGPORT", "1")
    response = TestClient(app).get("/patients/search")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database is unavailable. Try again later."}


# --- real SQL against a throwaway schema

# (encounter_id, patient_nbr, risk_score, risk_level, queued?)
SEARCH_ROWS = [
    (1, 100, 0, "LOW", False),
    (2, 100, 4, "MEDIUM", True),
    (3, 200, 5, "HIGH", True),
    (4, 100, 8, "HIGH", True),
    (5, 200, 3, "MEDIUM", True),
    (6, 300, 2, "LOW", False),
    (7, 100, 5, "HIGH", True),
]


@pytest.fixture(scope="module")
def db_client():
    load_env()
    schema = f"test_{uuid.uuid4().hex[:8]}"
    try:
        admin = psycopg.connect(autocommit=True, connect_timeout=5)
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL is not reachable")
    with admin:
        admin.execute(f"CREATE SCHEMA {schema}")
        try:
            admin.execute(f"SET search_path TO {schema}")
            admin.execute(SCHEMA_SQL.read_text())
            admin.execute(SEED_SQL.read_text())
            with admin.cursor() as cur:
                cur.executemany(
                    "INSERT INTO patient_encounters (encounter_id, patient_nbr, risk_score, risk_level) "
                    "VALUES (%s, %s, %s, %s)",
                    [row[:4] for row in SEARCH_ROWS],
                )
                cur.executemany("INSERT INTO care_interventions (encounter_id) VALUES (%s)",
                                [(row[0],) for row in SEARCH_ROWS if row[4]])
            mp = pytest.MonkeyPatch()
            mp.setenv("PGOPTIONS", f"-c search_path={schema}")
            try:
                yield TestClient(app)
            finally:
                mp.undo()
        finally:
            admin.execute(f"DROP SCHEMA {schema} CASCADE")


def search_ids(client, **params):
    response = client.get("/patients/search", params=params)
    assert response.status_code == 200
    return [row["encounter_id"] for row in response.json()]


def test_db_orders_high_medium_low_then_score_desc_then_id(db_client):
    assert search_ids(db_client) == [4, 3, 7, 2, 5, 6, 1]


def test_db_filters_combine_with_and(db_client):
    assert search_ids(db_client, patient_nbr=100) == [4, 7, 2, 1]
    assert search_ids(db_client, patient_nbr=100, risk_level="HIGH") == [4, 7]
    assert search_ids(db_client, patient_nbr=100, risk_level="HIGH", risk_score=5) == [7]
    assert search_ids(db_client, risk_score=5) == [3, 7]


def test_db_paging(db_client):
    assert search_ids(db_client, limit=3) == [4, 3, 7]
    assert search_ids(db_client, limit=3, offset=3) == [2, 5, 6]


def test_db_no_match_is_empty_list(db_client):
    assert search_ids(db_client, patient_nbr=999) == []


def test_db_low_row_has_null_intervention_and_queued_row_has_status(db_client):
    rows = {row["encounter_id"]: row for row in db_client.get("/patients/search").json()}
    assert all(rows[1][field] is None
               for field in ("intervention_id", "status", "intervention_status", "assigned_to", "notes"))
    assert rows[4]["status"] == rows[4]["intervention_status"] == "PENDING_REVIEW"
    assert isinstance(rows[4]["intervention_id"], int)
    assert "num_procedures" not in rows[4] and "created_at" not in rows[4]
