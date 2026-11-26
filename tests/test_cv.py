import json

import pytest
from fastapi.testclient import TestClient

from jobradar import cv
from jobradar.api import app, get_conn, get_cv_base, get_llm
from jobradar.db import init_db, save_jobs
from jobradar.parser import Job
from test_llm import DESCRIPTION, FakeLLM

T = lambda s: {"fr": s + " (fr)", "en": s}
BASE = {
    "contact": {"name": "Test Person", "location": T("Brussels"), "phone": "+32 0", "email": "a@b.c", "website": "x.be"},
    "experiences": [
        {"id": "main", "always": True, "role": T("Engineer"), "org": T("Org"), "dates": T("2025"),
         "bullets": [{"id": "m1", **T("Built <agents>")}, {"id": "m2", **T("Websites")}]},
        {"id": "side", "role": T("Project"), "org": T("Perso"), "dates": T("2026"),
         "bullets": [{"id": "s1", **T("FastAPI app")}]},
        {"id": "sony", "always": True, "role": T("Intern"), "org": T("Sony"), "dates": T("2022"),
         "bullets": [{"id": "y1", **T("ML models")}]},
    ],
    "skills": [{"id": "ml", "label": T("ML"), "items": ["Python", "SQL"]},
               {"id": "dev", "label": T("Dev"), "items": ["FastAPI", "React"]}],
    "learning": T("RAG"),
    "education": {"degree": T("MSc"), "school": T("ECAM"), "year": "2024", "detail": T("ML")},
    "languages": T("French, English"),
}
PLAN = {"language": "en", "headline": "Data Scientist · Python", "summary": "I build things.",
        "experiences": [{"id": "side", "bullets": ["s1"]}, {"id": "main", "bullets": ["m1", "invented"]},
                        {"id": "ghost", "bullets": ["g1"]}],
        "skills": [{"id": "dev", "items": ["FastAPI", "Kubernetes"]}, {"id": "nope", "items": ["Rust"]}],
        "missing": ["Kubernetes"]}


def test_clean_plan_drops_inventions():
    plan = cv.clean_plan(PLAN, BASE)
    assert [e["id"] for e in plan["experiences"]] == ["main", "side", "sony"]  # ordre de la base, sony obligatoire
    assert plan["experiences"][0]["bullets"] == ["m1"]                         # puce inventée retirée
    assert plan["experiences"][2]["bullets"] == ["y1"]
    assert plan["skills"] == [{"id": "dev", "items": ["FastAPI"]}]             # Kubernetes et Rust retirés


def test_render_escapes_and_uses_language():
    plan = cv.clean_plan({**PLAN, "language": "fr", "summary": "<script>x</script>"}, BASE)
    html = cv.render_html(plan, BASE, {"company": "Sia"})
    assert "<script>x" not in html and "&lt;script&gt;" in html
    assert "Built &lt;agents&gt; (fr)" in html
    assert "Kubernetes" in html  # affiché seulement dans la note "absent de ta base", masquée à l'impression


@pytest.fixture
def client():
    conn = init_db(":memory:")
    save_jobs(conn, [Job("1", "Data Scientist", "Sia", "Bruxelles", "Hybride", "https://x/1")])
    llm = FakeLLM(PLAN)
    app.dependency_overrides[get_conn] = lambda: conn
    app.dependency_overrides[get_llm] = lambda: llm
    app.dependency_overrides[get_cv_base] = lambda: BASE
    yield TestClient(app), llm
    app.dependency_overrides.clear()


def test_cv_needs_description(client):
    c, _ = client
    assert c.post("/jobs/1/cv", json={}).status_code == 400


def test_cv_generate_and_show(client):
    c, llm = client
    r = c.post("/jobs/1/cv", json={"description": DESCRIPTION})
    assert r.status_code == 200
    assert json.loads(r.json()["cv_plan"])["experiences"][0]["id"] == "main"
    assert "a@b.c" not in llm.last["messages"][1]["content"]  # pas de coordonnées envoyées au LLM
    page = c.get("/jobs/1/cv")
    assert page.status_code == 200 and "Test Person" in page.text and "FastAPI app" in page.text


def test_cv_reuses_saved_description(client):
    c, _ = client
    c.post("/jobs/1/cv", json={"description": DESCRIPTION})
    assert c.post("/jobs/1/cv", json={}).status_code == 200


def test_show_cv_before_generation(client):
    c, _ = client
    assert c.get("/jobs/1/cv").status_code == 404


def test_too_few_bullets_are_completed(monkeypatch):
    monkeypatch.setattr(cv, "MIN_BULLETS", {"main": 2})
    plan = cv.clean_plan({**PLAN, "experiences": [{"id": "main", "bullets": ["m2"]}]}, BASE)
    assert plan["experiences"][0]["bullets"] == ["m2", "m1"]  # choix du LLM d'abord, puis complété


def test_save_and_show_sent_cv(client):
    c, _ = client
    c.post("/jobs/1/cv", json={"description": DESCRIPTION})
    html = "<h1>Test Person</h1><p>Version retouchée à la main pour Sia</p>"
    r = c.post("/jobs/1/cv/sent", json={"html": html, "mark_applied": True})
    assert r.status_code == 200
    assert r.json()["status"] == "applied" and r.json()["cv_sent_at"]
    assert "cv_sent_html" not in r.json()
    page = c.get("/jobs/1/cv/sent").text
    assert "retouchée à la main" in page and 'contenteditable="true"' not in page
    assert "cv_sent_html" not in c.get("/jobs").json()[0]


def test_save_sent_cv_without_status_change(client):
    c, _ = client
    r = c.post("/jobs/1/cv/sent", json={"html": "x" * 60, "mark_applied": False})
    assert r.json()["status"] == "new"


def test_no_sent_cv_yet(client):
    c, _ = client
    assert c.get("/jobs/1/cv/sent").status_code == 404
