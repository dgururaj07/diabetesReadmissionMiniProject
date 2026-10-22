import uuid
from datetime import datetime, timedelta
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from api.db import load_env
from api.main import app

SQL_DIR = Path(__file__).parent.parent / "sql"
SCHEMA_SQL = SQL_DIR / "01_create_schema.sql"
SEED_SQL = SQL_DIR / "02_seed_intervention_statuses.sql"
ROWS = 120  # encounter_id 1..120, so the default page size of 50 is exercised

LEVELS = ["LOW", "MEDIUM", "HIGH"]
OUTCOMES = ["<30", ">30", "NO", "NO"]
STATUSES = ["ASSIGNED", "CONTACTED", "PENDING_REVIEW", "FOLLOW_UP_SCHEDULED"]
ASSIGNEES = ["nurse", "doctor"]
STALE_LOW_ID = 6  # LOW encounter given an intervention row anyway; it must stay out of the queue
BASE_TIME = datetime(2026, 1, 1)


def created_at(i):
    # Higher encounter_id = older intervention, so queue order differs from encounter_id order.
    return BASE_TIME - timedelta(minutes=i)


@pytest.fixture(scope="module")
def client():
    """Run the API against a throwaway schema built from sql/01_create_schema.sql.

    PGOPTIONS points search_path at the scratch schema, so the real tables are never read or written."""
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
                    "INSERT INTO patient_encounters (encounter_id, patient_nbr, risk_score, risk_level, readmitted) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    [(i, 1000 + i, i % 7, LEVELS[i % 3], OUTCOMES[i % 4]) for i in range(1, ROWS + 1)],
                )
            with admin.cursor() as cur:
                cur.executemany(
                    "INSERT INTO care_interventions (encounter_id, status, assigned_to, notes, created_at, updated_at) "
                    "VALUES (%s, %s, %s, 'call patient', %s, %s)",
                    [(i, STATUSES[i % 4], ASSIGNEES[i % 2], created_at(i), created_at(i))
                     for i in range(1, ROWS + 1) if LEVELS[i % 3] != "LOW" or i == STALE_LOW_ID],
                )
            mp = pytest.MonkeyPatch()
            mp.setenv("PGOPTIONS", f"-c search_path={schema}")
            try:
                yield TestClient(app)
            finally:
                mp.undo()
        finally:
            admin.execute(f"DROP SCHEMA {schema} CASCADE")


def ids(response):
    return [row["encounter_id"] for row in response.json()]


def expected(level=None, outcome=None):
    return [i for i in range(1, ROWS + 1)
            if (level is None or LEVELS[i % 3] == level) and (outcome is None or OUTCOMES[i % 4] == outcome)]


def test_no_filters_ordered_and_capped_at_50(client):
    response = client.get("/encounters")
    assert response.status_code == 200
    assert ids(response) == list(range(1, 51))


def test_returns_all_columns(client):
    row = client.get("/encounters", params={"limit": 1}).json()[0]
    assert {"encounter_id", "patient_nbr", "age", "readmitted", "risk_score", "risk_level",
            "review_reason", "created_at"} <= row.keys()


@pytest.mark.parametrize("level", LEVELS)
def test_risk_level_filter(client, level):
    response = client.get("/encounters", params={"risk_level": level, "limit": 500})
    assert ids(response) == expected(level=level)


@pytest.mark.parametrize("outcome", ["<30", ">30", "NO"])
def test_readmitted_filter(client, outcome):
    response = client.get("/encounters", params={"readmitted": outcome, "limit": 500})
    assert ids(response) == expected(outcome=outcome)


def test_filters_combine_with_and(client):
    response = client.get("/encounters", params={"risk_level": "HIGH", "readmitted": "NO", "limit": 500})
    assert ids(response) == expected(level="HIGH", outcome="NO")
    assert ids(response)


def test_pages_do_not_overlap(client):
    page1 = ids(client.get("/encounters", params={"limit": 10, "offset": 0}))
    page2 = ids(client.get("/encounters", params={"limit": 10, "offset": 10}))
    assert page1 == list(range(1, 11))
    assert page2 == list(range(11, 21))
    assert not set(page1) & set(page2)


def test_offset_past_end_is_empty_list(client):
    response = client.get("/encounters", params={"offset": ROWS})
    assert response.status_code == 200
    assert response.json() == []


def test_filter_matching_nothing_returns_empty_list(client):
    response = client.get("/encounters", params={"risk_level": "HIGH", "readmitted": "<30", "offset": 500})
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize("params", [
    {"risk_level": "URGENT"},
    {"readmitted": "MAYBE"},
    {"limit": 0},
    {"limit": 501},
    {"offset": -1},
])
def test_invalid_parameters_return_422(client, params):
    assert client.get("/encounters", params=params).status_code == 422


def test_sql_injection_attempt_is_rejected_by_validation(client):
    assert client.get("/encounters", params={"risk_level": "HIGH' OR '1'='1"}).status_code == 422


def test_database_down_returns_503(monkeypatch):
    load_env()
    monkeypatch.setenv("PGPORT", "1")
    response = TestClient(app).get("/encounters")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database is unavailable. Try again later."}


INTERVENTION_FIELDS = ["intervention_id", "intervention_status", "assigned_to", "intervention_notes",
                       "intervention_created_at", "intervention_updated_at"]


def test_encounter_with_intervention(client):
    response = client.get("/encounters/2")  # LEVELS[2 % 3] == HIGH
    assert response.status_code == 200
    body = response.json()
    assert body["encounter_id"] == 2
    assert body["risk_level"] == "HIGH"
    assert all(body[f] is not None for f in INTERVENTION_FIELDS)
    assert body["intervention_status"] == "PENDING_REVIEW"
    assert body["assigned_to"] == "nurse"
    assert body["intervention_notes"] == "call patient"
    assert body["created_at"] is not None  # the encounter's own created_at keeps its name


def test_encounter_without_intervention_has_null_fields(client):
    response = client.get("/encounters/3")  # LEVELS[3 % 3] == LOW
    assert response.status_code == 200
    body = response.json()
    assert body["risk_level"] == "LOW"
    assert all(body[f] is None for f in INTERVENTION_FIELDS)


def test_unknown_encounter_returns_404(client):
    response = client.get("/encounters/999999")
    assert response.status_code == 404
    assert response.json() == {"detail": "Encounter 999999 not found"}


def test_non_integer_encounter_id_returns_422(client):
    assert client.get("/encounters/abc").status_code == 422


def test_list_endpoint_still_works_alongside_detail(client):
    response = client.get("/encounters", params={"limit": 3})
    assert response.status_code == 200
    assert ids(response) == [1, 2, 3]


def test_detail_database_down_returns_503(monkeypatch):
    load_env()
    monkeypatch.setenv("PGPORT", "1")
    assert TestClient(app).get("/encounters/1").status_code == 503


QUEUE_FIELDS = {"encounter_id", "patient_nbr", "age", "risk_score", "risk_level", "review_reason",
                "intervention_id", "status", "assigned_to", "notes", "created_at", "updated_at"}


def expected_queue(level=None, status=None, assignee=None):
    """Encounter ids in queue order: HIGH first, then oldest intervention (highest id) first."""
    wanted = [i for i in range(1, ROWS + 1)
              if LEVELS[i % 3] != "LOW"
              and (level is None or LEVELS[i % 3] == level)
              and (status is None or STATUSES[i % 4] == status)
              and (assignee is None or ASSIGNEES[i % 2] == assignee)]
    return sorted(wanted, key=lambda i: (LEVELS[i % 3] != "HIGH", -i))


def queue_ids(client, **params):
    response = client.get("/care-queue", params={"limit": 500, **params})
    assert response.status_code == 200
    return ids(response)


def test_queue_has_only_medium_and_high_high_first_then_oldest(client):
    result = queue_ids(client)
    assert result == expected_queue()
    levels = [LEVELS[i % 3] for i in result]
    assert set(levels) == {"HIGH", "MEDIUM"}
    assert levels == sorted(levels, key=lambda lv: lv != "HIGH")


def test_queue_excludes_low_with_stale_intervention(client):
    assert LEVELS[STALE_LOW_ID % 3] == "LOW"
    assert STALE_LOW_ID not in queue_ids(client)
    assert client.get(f"/encounters/{STALE_LOW_ID}").json()["intervention_id"] is not None


@pytest.mark.parametrize("level", ["MEDIUM", "HIGH"])
def test_queue_risk_level_filter(client, level):
    assert queue_ids(client, risk_level=level) == expected_queue(level=level)


def test_queue_low_returns_empty_list(client):
    response = client.get("/care-queue", params={"risk_level": "LOW"})
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize("status", STATUSES)
def test_queue_status_filter(client, status):
    assert queue_ids(client, status=status) == expected_queue(status=status)


def test_queue_assigned_to_filter_is_exact_and_case_sensitive(client):
    assert queue_ids(client, assigned_to="nurse") == expected_queue(assignee="nurse")
    assert queue_ids(client, assigned_to="Nurse") == []


def test_queue_filters_combine_with_and(client):
    result = queue_ids(client, risk_level="HIGH", status="ASSIGNED", assigned_to="nurse")
    assert result == expected_queue(level="HIGH", status="ASSIGNED", assignee="nurse")
    assert result


def test_queue_pages_do_not_overlap(client):
    everything = expected_queue()
    page1 = ids(client.get("/care-queue", params={"limit": 10, "offset": 0}))
    page2 = ids(client.get("/care-queue", params={"limit": 10, "offset": 10}))
    assert page1 == everything[:10]
    assert page2 == everything[10:20]
    assert not set(page1) & set(page2)


def test_queue_default_page_size_is_50(client):
    assert len(client.get("/care-queue").json()) == min(50, len(expected_queue()))


def test_queue_items_have_exactly_the_12_fields(client):
    items = client.get("/care-queue", params={"limit": 3}).json()
    assert items
    assert all(set(item) == QUEUE_FIELDS for item in items)


@pytest.mark.parametrize("params", [
    {"risk_level": "URGENT"},
    {"status": "DONE"},
    {"limit": 0},
    {"limit": 501},
    {"offset": -1},
])
def test_queue_invalid_parameters_return_422(client, params):
    assert client.get("/care-queue", params=params).status_code == 422


def test_queue_database_down_returns_503(monkeypatch):
    load_env()
    monkeypatch.setenv("PGPORT", "1")
    assert TestClient(app).get("/care-queue").status_code == 503
