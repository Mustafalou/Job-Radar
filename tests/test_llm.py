import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from jobradar import llm_scoring
from jobradar.api import app, get_conn, get_llm
from jobradar.db import init_db, save_jobs, set_score
from jobradar.parser import Job

DESCRIPTION = "We are looking for a junior data scientist with Python, scikit-learn and SQL. " * 3
ANSWER = {"score": 82, "verdict": "Bon match, postuler.", "strengths": ["Python", "ML"],
          "gaps": ["Databricks"], "blockers": []}


class FakeLLM:
    """Imite client.chat.completions.create et garde la dernière requête."""
    def __init__(self, answer):
        self.answer, self.last = answer, None
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs):
        self.last = kwargs
        msg = SimpleNamespace(content=json.dumps(self.answer))
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


@pytest.fixture
def setup():
    conn = init_db(":memory:")
    save_jobs(conn, [Job("1", "Data Scientist", "Sia", "Bruxelles", "Hybride", "https://www.linkedin.com/jobs/view/1/")])
    set_score(conn, "1", 90, [])
    conn.commit()
    llm = FakeLLM(ANSWER)
    app.dependency_overrides[get_conn] = lambda: conn
    app.dependency_overrides[get_llm] = lambda: llm
    yield TestClient(app), llm
    app.dependency_overrides.clear()


def test_analyze_saves_result(setup, monkeypatch):
    client, llm = setup
    monkeypatch.setattr(llm_scoring, "load_profile", lambda: "Profil de test")
    r = client.post("/jobs/1/analyze", json={"description": DESCRIPTION})
    assert r.status_code == 200
    job = r.json()
    assert job["llm_score"] == 82
    assert json.loads(job["llm_analysis"])["gaps"] == ["Databricks"]
    assert job["description"] == DESCRIPTION
    prompt = llm.last["messages"][1]["content"]
    assert "Profil de test" in prompt and "Sia" in prompt


def test_analyze_unknown_job(setup):
    client, _ = setup
    assert client.post("/jobs/999/analyze", json={"description": DESCRIPTION}).status_code == 404


def test_analyze_description_too_short(setup):
    client, _ = setup
    assert client.post("/jobs/1/analyze", json={"description": "trop court"}).status_code == 422


def test_score_is_clamped():
    llm = FakeLLM({**ANSWER, "score": 140})
    result = llm_scoring.analyze_job({"title": "X"}, DESCRIPTION, client=llm, profile="p")
    assert result["score"] == 100


def test_not_configured_returns_503(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    llm_scoring.get_client.cache_clear()
    conn = init_db(":memory:")
    app.dependency_overrides[get_conn] = lambda: conn
    try:
        r = TestClient(app).post("/jobs/1/analyze", json={"description": DESCRIPTION})
        assert r.status_code == 503
    finally:
        app.dependency_overrides.clear()
