"""Étape 4 : API FastAPI. Lance : uvicorn jobradar.api:app --reload  puis http://127.0.0.1:8000

- GET  /jobs                 (FAIT)   liste des offres triées par score
- PATCH /jobs/{job_id}       (FAIT)   changer le statut d'une offre (+ date du changement, UTC)
- POST /jobs/{job_id}/analyze        analyse de l'offre par le LLM, à partir de la description collée
- GET  /                     (FAIT)   le petit tableau de bord HTML
- Doc interactive auto       http://127.0.0.1:8000/docs
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from jobradar import llm_scoring
from jobradar.db import init_db

app = FastAPI(title="Job Radar")
STATIC = Path(__file__).parent / "static"

Status = Literal["new", "interested", "applied", "rejected"]


def get_conn() -> sqlite3.Connection:
    """Dépendance FastAPI : fournit la connexion à la base (remplacée dans les tests)."""
    return init_db()


def get_llm():
    """Dépendance FastAPI : client LLM (remplacé par un faux client dans les tests)."""
    try:
        return llm_scoring.get_client()
    except llm_scoring.LLMNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))


class StatusUpdate(BaseModel):
    status: Status


class AnalyzeRequest(BaseModel):
    description: str = Field(min_length=50, description="Texte de l'offre copié depuis LinkedIn")


@app.get("/")
def dashboard():
    return FileResponse(STATIC / "index.html")


@app.get("/jobs")
def list_jobs(
    min_score: float = 0,
    status: Status | None = None,
    limit: int = 50,
    conn: sqlite3.Connection = Depends(get_conn),
):
    query = "SELECT * FROM jobs WHERE COALESCE(score, 0) >= ?"
    params: list = [min_score]
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY score DESC LIMIT ?"
    params.append(limit)
    return [dict(r) for r in conn.execute(query, params).fetchall()]


@app.patch("/jobs/{job_id}")
def update_status(job_id: str, body: StatusUpdate, conn: sqlite3.Connection = Depends(get_conn)):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")  # UTC : la page convertit en heure locale
    cur = conn.execute(
        "UPDATE jobs SET status = ?, status_updated_at = ? WHERE job_id = ?",
        (body.status, now, job_id),
    )
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Offre introuvable")
    conn.commit()
    row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
    return dict(row)


@app.post("/jobs/{job_id}/analyze")
def analyze(job_id: str, body: AnalyzeRequest, conn: sqlite3.Connection = Depends(get_conn), llm=Depends(get_llm)):
    row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Offre introuvable")
    try:
        result = llm_scoring.analyze_job(dict(row), body.description, client=llm)
    except Exception as e:  # quota, réseau, réponse invalide... on renvoie un message lisible
        raise HTTPException(status_code=502, detail=f"Erreur du LLM : {e}")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.execute(
        "UPDATE jobs SET description = ?, llm_score = ?, llm_analysis = ?, llm_analyzed_at = ? WHERE job_id = ?",
        (body.description, result["score"], json.dumps(result, ensure_ascii=False), now, job_id),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone())
