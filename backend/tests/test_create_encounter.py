import uuid
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from api import repository
from api.db import load_env
from api.main import app

SQL_DIR = Path(__file__).parent.parent / "sql"
SCHEMA_SQL = SQL_DIR / "01_create_schema.sql"
SEED_SQL = SQL_DIR / "02_seed_intervention_statuses.sql"

ALL_RULES = {"number_inpatient": 3, "number_emergency": 2, "number_outpatient": 3,
             "time_in_hospital": 7, "num_medications": 20}


@pytest.fixture(scope="module")
def client():
    """Run the API against an empty throwaway schema, so created rows never touch the real tables."""
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
            mp = pytest.MonkeyPatch()
            mp.setenv("PGOPTIONS", f"-c search_path={schema}")
            try:
                yield TestClient(app)
            finally:
                mp.undo()
        finally:
            admin.execute(f"DROP SCHEMA {schema} CASCADE")


def create(client, body):
    return client.post("/encounters", json=body)


def test_low_risk_is_not_queued(client):
    response = create(client, {"patient_nbr": 123})
    assert response.status_code == 201
    body = response.json()
    assert body["patient_nbr"] == 123
    assert body["risk_score"] == 0
    assert body["risk_level"] == "LOW"
    assert body["review_reason"] == "No prioritization rules triggered"
    assert body["intervention_id"] is None
    assert body["status"] is None
    # defaults are stored
    assert body["time_in_hospital"] == 0
    assert body["admission_type_id"] == 1
    assert body["discharge_disposition_id"] == 1
    assert body["readmitted"] == "NO"
    assert body["created_at"] is not None
    detail = client.get(f"/encounters/{body['encounter_id']}").json()
    assert detail["intervention_id"] is None


def test_medium_risk_is_queued_pending_review(client):
    body = create(client, {"patient_nbr": 1, "number_inpatient": 3}).json()
    assert body["risk_score"] == 3
    assert body["risk_level"] == "MEDIUM"
    assert body["status"] == "PENDING_REVIEW"
    assert isinstance(body["intervention_id"], int)
    queue = client.get("/care-queue", params={"risk_level": "MEDIUM"}).json()
    assert body["encounter_id"] in [item["encounter_id"] for item in queue]


def test_high_risk(client):
    body = create(client, {"patient_nbr": 1, "number_inpatient": 3, "number_emergency": 2}).json()
    assert body["risk_score"] == 5
    assert body["risk_level"] == "HIGH"
    assert body["review_reason"] == "3+ prior inpatient visits; 2+ emergency visits"
    assert body["status"] == "PENDING_REVIEW"


def test_every_rule_gives_max_score_8(client):
    body = create(client, {"patient_nbr": 1, **ALL_RULES}).json()
    assert body["risk_score"] == 8
    assert body["risk_level"] == "HIGH"


def test_example_request_from_contract(client):
    response = create(client, {"patient_nbr": 88888, "age": "[60-70)", "time_in_hospital": 8,
                               "number_inpatient": 3, "number_emergency": 2, "num_medications": 22})
    assert response.status_code == 201
    body = response.json()
    assert body["risk_score"] == 7
    assert body["risk_level"] == "HIGH"
    assert body["review_reason"] == ("3+ prior inpatient visits; 2+ emergency visits; "
                                     "7+ days in hospital; 20+ medications")
    assert body["status"] == "PENDING_REVIEW"
    assert body["age"] == "[60-70)"


def test_encounter_ids_increase_by_one(client):
    first = create(client, {"patient_nbr": 5}).json()["encounter_id"]
    second = create(client, {"patient_nbr": 5}).json()["encounter_id"]
    assert second == first + 1


SCORE_FIELDS = ["risk_score", "risk_level", "review_reason", "patient_nbr", "time_in_hospital",
                "number_inpatient", "number_emergency", "num_medications"]


@pytest.mark.parametrize("patient_alias", ["patient_number", "patient-number"])
def test_aliases_match_canonical_names(client, patient_alias):
    canonical = create(client, {"patient_nbr": 7, "number_inpatient": 4, "number_emergency": 2,
                                "time_in_hospital": 7, "num_medications": 20}).json()
    aliased = create(client, {patient_alias: 7, "inpatient": 4, "emergency": 2,
                              "hospital": 7, "medications": 20}).json()
    assert {f: aliased[f] for f in SCORE_FIELDS} == {f: canonical[f] for f in SCORE_FIELDS}


def test_canonical_name_wins_over_alias(client):
    body = create(client, {"patient_nbr": 9, "patient_number": 10, "number_inpatient": 0, "inpatient": 5}).json()
    assert body["patient_nbr"] == 9
    assert body["number_inpatient"] == 0
    assert body["risk_level"] == "LOW"


def test_readmitted_is_stored_but_never_scored(client):
    base = {"patient_nbr": 1, "number_inpatient": 3}
    without = create(client, base).json()
    with_outcome = create(client, {**base, "readmitted": "<30"}).json()
    assert with_outcome["readmitted"] == "<30"
    assert {f: with_outcome[f] for f in ("risk_score", "risk_level", "review_reason")} == \
           {f: without[f] for f in ("risk_score", "risk_level", "review_reason")}


@pytest.mark.parametrize("body", [{"patient_nbr": 0}, {"patient_nbr": -5}, {}, {"patient_nbr": None}])
def test_missing_or_non_positive_patient_returns_400(client, body):
    response = create(client, body)
    assert response.status_code == 400
    assert response.json() == {"detail": "Patient Number must be a positive integer."}


@pytest.mark.parametrize("body", [
    {"patient_nbr": 1, "number_inpatient": -1},
    {"patient_nbr": 1, "num_medications": "many"},
    {"patient_nbr": "abc"},
    {"patient_nbr": 1, "readmitted": "MAYBE"},
    {"patient_nbr": 1, "age": "x" * 31},
])
def test_invalid_body_returns_422(client, body):
    assert create(client, body).status_code == 422


def test_rejected_requests_store_nothing(client):
    before = len(client.get("/encounters", params={"limit": 500}).json())
    create(client, {"patient_nbr": 0})
    create(client, {"patient_nbr": 1, "number_inpatient": -1})
    assert len(client.get("/encounters", params={"limit": 500}).json()) == before


def test_insert_returning_no_row_returns_400(monkeypatch):
    monkeypatch.setattr(repository, "create_encounter", lambda encounter: None)
    response = TestClient(app).post("/encounters", json={"patient_nbr": 1})
    assert response.status_code == 400
    assert response.json() == {"detail": "Failed to create encounter"}


def test_create_database_down_returns_503(monkeypatch):
    load_env()
    monkeypatch.setenv("PGPORT", "1")
    response = TestClient(app).post("/encounters", json={"patient_nbr": 1})
    assert response.status_code == 503
    assert response.json() == {"detail": "Database is unavailable. Try again later."}
