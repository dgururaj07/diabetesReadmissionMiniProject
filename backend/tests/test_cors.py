import pytest
from fastapi.testclient import TestClient

from api.main import ALLOWED_ORIGINS, app

client = TestClient(app)


@pytest.mark.parametrize("origin", ALLOWED_ORIGINS)
def test_allowed_origin_gets_cors_header(origin):
    response = client.get("/health", headers={"Origin": origin})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "access-control-allow-credentials" not in response.headers


def test_preflight_for_patch_is_allowed():
    # The middleware answers the preflight itself, so the route and database are never reached.
    response = client.options("/interventions/2", headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "PATCH",
        "Access-Control-Request-Headers": "content-type",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "PATCH" in response.headers["access-control-allow-methods"]
    assert "content-type" in response.headers["access-control-allow-headers"].lower()


def test_disallowed_origin_gets_no_cors_header():
    response = client.get("/health", headers={"Origin": "http://evil.example"})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_disallowed_origin_preflight_is_rejected():
    response = client.options("/interventions/2", headers={
        "Origin": "http://evil.example",
        "Access-Control-Request-Method": "PATCH",
    })
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_request_without_origin_works_normally():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "access-control-allow-origin" not in response.headers


def test_cors_middleware_added_once():
    assert sum(m.cls.__name__ == "CORSMiddleware" for m in app.user_middleware) == 1
