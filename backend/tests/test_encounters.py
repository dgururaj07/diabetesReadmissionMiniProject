import uuid
from datetime import datetime, timedelta
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from api.db import load_env
from api import service
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


def high_queue_ids(client, **params):
    response = client.get("/care-queue/high", params={"limit": 500, **params})
    assert response.status_code == 200
    return ids(response)


def test_high_queue_has_only_high_items(client):
    result = high_queue_ids(client)
    assert result == expected_queue(level="HIGH")
    assert result
    assert all(LEVELS[i % 3] == "HIGH" for i in result)


@pytest.mark.parametrize("params, kwargs", [
    ({"status": "ASSIGNED"}, {"status": "ASSIGNED"}),
    ({"assigned_to": "nurse"}, {"assignee": "nurse"}),
    ({"status": "ASSIGNED", "assigned_to": "nurse"}, {"status": "ASSIGNED", "assignee": "nurse"}),
])
def test_high_queue_filters_alone_and_combined(client, params, kwargs):
    result = high_queue_ids(client, **params)
    assert result == expected_queue(level="HIGH", **kwargs)
    assert result


def test_high_queue_assigned_to_is_case_sensitive(client):
    assert high_queue_ids(client, assigned_to="Nurse") == []


@pytest.mark.parametrize("params", [
    {},
    {"status": "CONTACTED"},
    {"assigned_to": "doctor"},
    {"status": "CONTACTED", "assigned_to": "doctor", "limit": 5, "offset": 2},
])
def test_high_queue_equals_care_queue_with_high_filter(client, params):
    high = client.get("/care-queue/high", params=params)
    general = client.get("/care-queue", params={"risk_level": "HIGH", **params})
    assert high.status_code == 200
    assert high.json() == general.json()


def test_high_queue_pages_do_not_overlap(client):
    everything = expected_queue(level="HIGH")
    page1 = ids(client.get("/care-queue/high", params={"limit": 10, "offset": 0}))
    page2 = ids(client.get("/care-queue/high", params={"limit": 10, "offset": 10}))
    assert page1 == everything[:10]
    assert page2 == everything[10:20]
    assert not set(page1) & set(page2)


def test_high_queue_ignores_risk_level_parameter(client):
    assert high_queue_ids(client, risk_level="MEDIUM") == expected_queue(level="HIGH")


def test_high_queue_empty_result_is_empty_list(client):
    response = client.get("/care-queue/high", params={"offset": ROWS})
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize("params", [
    {"status": "DONE"},
    {"limit": 0},
    {"limit": 501},
    {"offset": -1},
])
def test_high_queue_invalid_parameters_return_422(client, params):
    assert client.get("/care-queue/high", params=params).status_code == 422


def test_high_queue_database_down_returns_503(monkeypatch):
    load_env()
    monkeypatch.setenv("PGPORT", "1")
    assert TestClient(app).get("/care-queue/high").status_code == 503


def test_care_queue_still_works_alongside_high_route(client):
    assert queue_ids(client) == expected_queue()


UPDATE_FIELDS = {"intervention_id", "encounter_id", "status", "assigned_to", "notes", "created_at", "updated_at"}
LOW_ID = 3  # LEVELS[3 % 3] == LOW, no intervention row
HIGH_ID = 2  # PENDING_REVIEW, nurse, notes "call patient"


@pytest.fixture
def restore_interventions(client):
    """PATCH tests change shared module data; put every intervention row back afterwards."""
    with psycopg.connect(autocommit=True) as conn:
        saved = conn.execute("SELECT encounter_id, status, assigned_to, notes, created_at, updated_at "
                             "FROM care_interventions").fetchall()
        yield conn
        conn.execute("DELETE FROM care_interventions WHERE encounter_id <> ALL(%s)", ([r[0] for r in saved],))
        with conn.cursor() as cur:
            cur.executemany("UPDATE care_interventions SET status = %s, assigned_to = %s, notes = %s, "
                            "created_at = %s, updated_at = %s WHERE encounter_id = %s",
                            [(*r[1:], r[0]) for r in saved])


def patch(client, encounter_id, body):
    return client.patch(f"/interventions/{encounter_id}", json=body)


def test_patch_status_only_moves_updated_at(client, restore_interventions):
    before = client.get(f"/encounters/{HIGH_ID}").json()
    response = patch(client, HIGH_ID, {"status": "CONTACTED"})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == UPDATE_FIELDS
    assert body["status"] == "CONTACTED"
    assert body["assigned_to"] == before["assigned_to"]
    assert body["notes"] == before["intervention_notes"]
    assert body["created_at"] == before["intervention_created_at"]
    assert body["updated_at"] > before["intervention_updated_at"]
    assert body["encounter_id"] == HIGH_ID
    assert body["intervention_id"] == before["intervention_id"]


def test_patch_assigned_to_only(client, restore_interventions):
    body = patch(client, HIGH_ID, {"assigned_to": "doctor"}).json()
    assert (body["status"], body["assigned_to"], body["notes"]) == ("PENDING_REVIEW", "doctor", "call patient")


def test_patch_notes_only(client, restore_interventions):
    body = patch(client, HIGH_ID, {"notes": "left voicemail"}).json()
    assert (body["status"], body["assigned_to"], body["notes"]) == ("PENDING_REVIEW", "nurse", "left voicemail")


def test_patch_all_fields_and_persists(client, restore_interventions):
    new = {"status": "CLOSED", "assigned_to": "doctor", "notes": "done"}
    body = patch(client, HIGH_ID, new).json()
    assert {k: body[k] for k in new} == new
    stored = client.get(f"/encounters/{HIGH_ID}").json()
    assert (stored["intervention_status"], stored["assigned_to"], stored["intervention_notes"]) == ("CLOSED", "doctor", "done")


def test_patch_null_field_keeps_old_value(client, restore_interventions):
    body = patch(client, HIGH_ID, {"status": "ASSIGNED", "assigned_to": None, "notes": None}).json()
    assert (body["status"], body["assigned_to"], body["notes"]) == ("ASSIGNED", "nurse", "call patient")


def test_patch_same_values_still_bumps_updated_at(client, restore_interventions):
    before = client.get(f"/encounters/{HIGH_ID}").json()
    body = patch(client, HIGH_ID, {"status": before["intervention_status"]}).json()
    assert body["updated_at"] > before["intervention_updated_at"]


def test_patch_does_not_touch_encounter(client, restore_interventions):
    before = client.get(f"/encounters/{HIGH_ID}").json()
    patch(client, HIGH_ID, {"status": "CLOSED", "notes": "x"})
    after = client.get(f"/encounters/{HIGH_ID}").json()
    for field in ("risk_score", "risk_level", "readmitted", "review_reason", "created_at"):
        assert after[field] == before[field]


@pytest.mark.parametrize("body", [{}, {"status": None, "assigned_to": None, "notes": None}])
def test_patch_without_any_field_returns_422(client, body):
    response = patch(client, HIGH_ID, body)
    assert response.status_code == 422
    assert "Provide at least one of: status, assigned_to, notes" in response.text


@pytest.mark.parametrize("body", [{"status": "DONE"}, {"assigned_to": "x" * 101}])
def test_patch_invalid_body_returns_422(client, body):
    assert patch(client, HIGH_ID, body).status_code == 422


def test_patch_assigned_to_100_characters_is_accepted(client, restore_interventions):
    assert patch(client, HIGH_ID, {"assigned_to": "x" * 100}).status_code == 200


def test_patch_non_integer_id_returns_422(client):
    assert client.patch("/interventions/abc", json={"status": "CLOSED"}).status_code == 422


def test_patch_unknown_encounter_returns_404(client):
    response = patch(client, 999999, {"status": "CLOSED"})
    assert response.status_code == 404
    assert response.json() == {"detail": "Encounter 999999 not found"}


def test_patch_low_encounter_without_intervention_returns_404_and_creates_nothing(client, restore_interventions):
    response = patch(client, LOW_ID, {"status": "CLOSED"})
    assert response.status_code == 404
    assert response.json() == {"detail": f"Encounter {LOW_ID} has no care intervention "
                                         "(only MEDIUM/HIGH risk encounters are queued)"}
    count = restore_interventions.execute("SELECT count(*) FROM care_interventions WHERE encounter_id = %s",
                                          (LOW_ID,)).fetchone()[0]
    assert count == 0


def test_patch_database_down_returns_503(monkeypatch):
    load_env()
    monkeypatch.setenv("PGPORT", "1")
    assert patch(TestClient(app), HIGH_ID, {"status": "CLOSED"}).status_code == 503


SUMMARY_FIELDS = {"total_encounters", "high_risk", "medium_risk", "low_risk", "pending_interventions",
                  "assigned_interventions", "contacted_interventions", "follow_up_scheduled",
                  "closed_interventions"}
COUNTS = {"total_encounters": 12, "high_risk": 4, "medium_risk": 5, "low_risk": 3}


def test_service_summary_with_all_statuses():
    rows = [{"status": "PENDING_REVIEW", "count": 1}, {"status": "ASSIGNED", "count": 2},
            {"status": "CONTACTED", "count": 3}, {"status": "FOLLOW_UP_SCHEDULED", "count": 4},
            {"status": "CLOSED", "count": 5}]
    assert service.build_operations_summary(COUNTS, rows) == {
        **COUNTS, "pending_interventions": 1, "assigned_interventions": 2, "contacted_interventions": 3,
        "follow_up_scheduled": 4, "closed_interventions": 5}


def test_service_summary_missing_statuses_are_zero():
    result = service.build_operations_summary(COUNTS, [{"status": "ASSIGNED", "count": 7}])
    assert result["assigned_interventions"] == 7
    assert [result[k] for k in ("pending_interventions", "contacted_interventions", "follow_up_scheduled",
                                "closed_interventions")] == [0, 0, 0, 0]


def test_service_summary_with_no_status_rows():
    result = service.build_operations_summary(COUNTS, [])
    assert {k: v for k, v in result.items() if k not in COUNTS} == dict.fromkeys(SUMMARY_FIELDS - COUNTS.keys(), 0)


def test_summary_has_exactly_the_9_integer_fields(client):
    response = client.get("/operations/summary")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == SUMMARY_FIELDS
    assert all(type(v) is int for v in body.values())


def test_summary_counts_match_data(client):
    body = client.get("/operations/summary").json()
    levels = [LEVELS[i % 3] for i in range(1, ROWS + 1)]
    with_intervention = [i for i in range(1, ROWS + 1) if LEVELS[i % 3] != "LOW" or i == STALE_LOW_ID]
    status_count = lambda s: sum(STATUSES[i % 4] == s for i in with_intervention)
    assert body["total_encounters"] == ROWS
    assert (body["high_risk"], body["medium_risk"], body["low_risk"]) == (
        levels.count("HIGH"), levels.count("MEDIUM"), levels.count("LOW"))
    assert body["pending_interventions"] == status_count("PENDING_REVIEW")
    assert body["assigned_interventions"] == status_count("ASSIGNED")
    assert body["contacted_interventions"] == status_count("CONTACTED")
    assert body["follow_up_scheduled"] == status_count("FOLLOW_UP_SCHEDULED")


def test_summary_risk_counts_add_up(client):
    body = client.get("/operations/summary").json()
    assert body["high_risk"] + body["medium_risk"] + body["low_risk"] == body["total_encounters"]


def test_summary_status_without_rows_is_zero(client):
    body = client.get("/operations/summary").json()
    assert "CLOSED" not in STATUSES  # fixture data has no CLOSED interventions
    assert body["closed_interventions"] == 0


@pytest.fixture
def empty_client():
    """Same scratch-schema approach as `client`, but with no encounters or interventions."""
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


def test_summary_on_empty_database_is_all_zeros(empty_client):
    response = empty_client.get("/operations/summary")
    assert response.status_code == 200
    assert response.json() == dict.fromkeys(SUMMARY_FIELDS, 0)


def test_summary_database_down_returns_503(monkeypatch):
    load_env()
    monkeypatch.setenv("PGPORT", "1")
    assert TestClient(app).get("/operations/summary").status_code == 503


ANALYSIS_FIELDS = {
    "overall_encounters": int, "overall_readmitted_under_30_days": int, "overall_readmission_rate": float,
    "high_risk_patients": int, "high_risk_readmitted_under_30_days": int, "high_risk_readmission_rate": float,
    "medium_risk_patients": int, "medium_risk_readmitted_under_30_days": int,
    "medium_risk_readmission_rate": float,
    "low_risk_patients": int, "low_risk_readmitted_under_30_days": int, "low_risk_readmission_rate": float,
    "note": str,
}
NOTE = "The historical readmitted field is used only for retrospective validation and is not used in risk scoring."
ZERO_ANALYSIS = {**{k: t() for k, t in ANALYSIS_FIELDS.items()}, "note": NOTE}


def group(level, encounters, readmitted):
    return {"risk_level": level, "encounters": encounters, "readmitted_under_30": readmitted}


def test_service_analysis_all_groups():
    result = service.build_readmission_analysis([group("HIGH", 4, 1), group("MEDIUM", 10, 2), group("LOW", 6, 0)])
    assert result == {
        "overall_encounters": 20, "overall_readmitted_under_30_days": 3, "overall_readmission_rate": 15.0,
        "high_risk_patients": 4, "high_risk_readmitted_under_30_days": 1, "high_risk_readmission_rate": 25.0,
        "medium_risk_patients": 10, "medium_risk_readmitted_under_30_days": 2, "medium_risk_readmission_rate": 20.0,
        "low_risk_patients": 6, "low_risk_readmitted_under_30_days": 0, "low_risk_readmission_rate": 0.0,
        "note": NOTE,
    }


def test_service_analysis_missing_group_is_zero():
    result = service.build_readmission_analysis([group("HIGH", 4, 1), group("LOW", 6, 0)])
    assert (result["medium_risk_patients"], result["medium_risk_readmitted_under_30_days"],
            result["medium_risk_readmission_rate"]) == (0, 0, 0.0)


def test_service_analysis_empty_list_is_all_zeros():
    assert service.build_readmission_analysis([]) == ZERO_ANALYSIS


def test_service_analysis_overall_is_sum_of_groups():
    result = service.build_readmission_analysis([group("HIGH", 7, 3), group("MEDIUM", 11, 2), group("LOW", 13, 1)])
    levels = ("high", "medium", "low")
    assert result["overall_encounters"] == sum(result[f"{lv}_risk_patients"] for lv in levels) == 31
    assert result["overall_readmitted_under_30_days"] == sum(
        result[f"{lv}_risk_readmitted_under_30_days"] for lv in levels) == 6


def test_service_analysis_rounds_to_2_decimals():
    assert service.build_readmission_analysis([group("HIGH", 3, 1)])["high_risk_readmission_rate"] == 33.33
    assert service.percentage(2, 3) == 66.67
    assert service.percentage(1, 0) == 0.0


def test_service_analysis_note_is_fixed_text():
    assert service.build_readmission_analysis([group("LOW", 1, 0)])["note"] == NOTE


def test_analysis_endpoint_fields_and_types(client):
    response = client.get("/operations/readmission-analysis")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == set(ANALYSIS_FIELDS)
    assert all(type(body[k]) is t for k, t in ANALYSIS_FIELDS.items())
    assert body["note"] == NOTE


def test_analysis_matches_sql_and_fixture_data(client):
    body = client.get("/operations/readmission-analysis").json()
    with psycopg.connect() as conn:
        under_30 = conn.execute("SELECT COUNT(*) FROM patient_encounters WHERE readmitted = '<30'").fetchone()[0]
    assert body["overall_readmitted_under_30_days"] == under_30
    assert body["overall_encounters"] == ROWS
    for level in LEVELS:
        in_level = [i for i in range(1, ROWS + 1) if LEVELS[i % 3] == level]
        assert body[f"{level.lower()}_risk_patients"] == len(in_level)
        assert body[f"{level.lower()}_risk_readmitted_under_30_days"] == sum(OUTCOMES[i % 4] == "<30" for i in in_level)


def test_analysis_only_under_30_counts_as_readmitted(empty_client):
    # empty_client's scratch schema is on PGOPTIONS, so this insert only touches throwaway tables.
    with psycopg.connect(autocommit=True) as conn, conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO patient_encounters (encounter_id, patient_nbr, risk_score, risk_level, readmitted) "
            "VALUES (%s, %s, 0, 'HIGH', %s)",
            [(1, 1, "<30"), (2, 2, ">30"), (3, 3, "NO"), (4, 4, None)],
        )
    body = empty_client.get("/operations/readmission-analysis").json()
    assert (body["high_risk_patients"], body["high_risk_readmitted_under_30_days"],
            body["high_risk_readmission_rate"]) == (4, 1, 25.0)
    assert (body["overall_encounters"], body["overall_readmitted_under_30_days"]) == (4, 1)


def test_analysis_on_empty_database_is_all_zeros(empty_client):
    response = empty_client.get("/operations/readmission-analysis")
    assert response.status_code == 200
    assert response.json() == ZERO_ANALYSIS


def test_analysis_database_down_returns_503(monkeypatch):
    load_env()
    monkeypatch.setenv("PGPORT", "1")
    assert TestClient(app).get("/operations/readmission-analysis").status_code == 503


DASHBOARD_FIELDS = {
    "total_diabetes_encounters": int, "readmitted_under_30_days": int, "readmission_rate": float,
    "high_risk_population": int, "high_risk_percent": float, "high_risk_30_day_readmissions": int,
    "care_queue_pending": int,
}
ZERO_DASHBOARD = {k: t() for k, t in DASHBOARD_FIELDS.items()}


def test_service_dashboard_normal_case():
    result = service.build_management_dashboard([group("HIGH", 4, 1), group("MEDIUM", 3, 1), group("LOW", 3, 0)], 5)
    assert result == {
        "total_diabetes_encounters": 10, "readmitted_under_30_days": 2, "readmission_rate": 20.0,
        "high_risk_population": 4, "high_risk_percent": 40.0, "high_risk_30_day_readmissions": 1,
        "care_queue_pending": 5,
    }


def test_service_dashboard_missing_high_is_zero():
    result = service.build_management_dashboard([group("MEDIUM", 3, 1), group("LOW", 3, 0)], 2)
    assert (result["high_risk_population"], result["high_risk_percent"],
            result["high_risk_30_day_readmissions"]) == (0, 0, 0.0)
    assert result["total_diabetes_encounters"] == 6


def test_service_dashboard_empty_is_all_zeros():
    assert service.build_management_dashboard([], 0) == ZERO_DASHBOARD


def test_service_dashboard_passes_pending_through():
    assert service.build_management_dashboard([], 17)["care_queue_pending"] == 17


def test_dashboard_endpoint_fields_and_types(client):
    response = client.get("/management/dashboard")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == set(DASHBOARD_FIELDS)
    assert all(type(body[k]) is t for k, t in DASHBOARD_FIELDS.items())


def test_dashboard_pending_matches_fixture_data(client):
    with_intervention = [i for i in range(1, ROWS + 1) if LEVELS[i % 3] != "LOW" or i == STALE_LOW_ID]
    expected = sum(STATUSES[i % 4] == "PENDING_REVIEW" for i in with_intervention)
    assert client.get("/management/dashboard").json()["care_queue_pending"] == expected


def test_dashboard_pending_counts_only_pending_review(empty_client):
    # empty_client's scratch schema is on PGOPTIONS, so these inserts only touch throwaway tables.
    statuses = ["PENDING_REVIEW", "PENDING_REVIEW", "ASSIGNED", "CONTACTED", "FOLLOW_UP_SCHEDULED", "CLOSED"]
    with psycopg.connect(autocommit=True) as conn, conn.cursor() as cur:
        cur.executemany("INSERT INTO patient_encounters (encounter_id, patient_nbr, risk_score, risk_level) "
                        "VALUES (%s, %s, 0, 'HIGH')", [(i, i) for i in range(1, len(statuses) + 1)])
        cur.executemany("INSERT INTO care_interventions (encounter_id, status) VALUES (%s, %s)",
                        list(enumerate(statuses, start=1)))
    assert empty_client.get("/management/dashboard").json()["care_queue_pending"] == 2


def test_dashboard_matches_readmission_analysis(client):
    dashboard = client.get("/management/dashboard").json()
    analysis = client.get("/operations/readmission-analysis").json()
    assert dashboard["total_diabetes_encounters"] == analysis["overall_encounters"]
    assert dashboard["readmitted_under_30_days"] == analysis["overall_readmitted_under_30_days"]
    assert dashboard["readmission_rate"] == analysis["overall_readmission_rate"]
    assert dashboard["high_risk_population"] == analysis["high_risk_patients"]
    assert dashboard["high_risk_30_day_readmissions"] == analysis["high_risk_readmitted_under_30_days"]


def test_dashboard_on_empty_database_is_all_zeros(empty_client):
    response = empty_client.get("/management/dashboard")
    assert response.status_code == 200
    assert response.json() == ZERO_DASHBOARD


def test_dashboard_database_down_returns_503(monkeypatch):
    load_env()
    monkeypatch.setenv("PGPORT", "1")
    assert TestClient(app).get("/management/dashboard").status_code == 503
