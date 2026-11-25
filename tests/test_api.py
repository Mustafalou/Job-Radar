import pytest
from fastapi.testclient import TestClient

from jobradar.api import app, get_conn
from jobradar.db import init_db, save_jobs, set_score
from jobradar.parser import Job


@pytest.fixture
def client():
    conn = init_db(":memory:")
    save_jobs(conn, [
        Job("1", "Data Scientist", "Sia", "Bruxelles", "Hybride", "https://www.linkedin.com/jobs/view/1/"),
        Job("2", "Senior AI Engineer", "Deloitte", "Zaventem", None, "https://www.linkedin.com/jobs/view/2/"),
    ])
    set_score(conn, "1", 90, [])
    set_score(conn, "2", 55, ["senior: -30"])
    conn.commit()
    app.dependency_overrides[get_conn] = lambda: conn
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_list_jobs_sorted(client):
    jobs = client.get("/jobs").json()
    assert [j["job_id"] for j in jobs] == ["1", "2"]


def test_min_score(client):
    assert len(client.get("/jobs?min_score=60").json()) == 1


def test_update_status(client):
    r = client.patch("/jobs/1", json={"status": "interested"})
    assert r.status_code == 200
    assert r.json()["status"] == "interested"
    assert r.json()["status_updated_at"] is not None
    assert len(client.get("/jobs?status=interested").json()) == 1


def test_update_unknown_job(client):
    assert client.patch("/jobs/999", json={"status": "applied"}).status_code == 404


def test_invalid_status(client):
    assert client.patch("/jobs/1", json={"status": "maybe"}).status_code == 422


def test_new_job_has_no_update_date(client):
    job = next(j for j in client.get("/jobs").json() if j["job_id"] == "2")
    assert job["status_updated_at"] is None
