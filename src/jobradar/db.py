"""Étape 2 : stocker les offres dans SQLite, sans doublons.

À TOI DE CODER les 3 fonctions ci-dessous avec le module standard `sqlite3`.

Rappels sqlite3 :
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS ...")
    conn.execute("INSERT ... VALUES (?, ?, ?)", (a, b, c))   # toujours des ? (jamais de f-string : injection SQL)
    conn.commit()
    rows = conn.execute("SELECT ...").fetchall()

Table `jobs` attendue :
    job_id     TEXT PRIMARY KEY   <- c'est elle qui empêche les doublons
    title, company, location, work_mode, url, source   TEXT
    first_seen TEXT                <- date ISO d'ajout, ex. datetime.now().isoformat()
    status     TEXT DEFAULT 'new'  <- new / interested / applied / rejected (servira plus tard)

Astuce doublons : "INSERT OR IGNORE" ne fait rien si le job_id existe déjà,
et `cursor.rowcount` vaut alors 0 (1 si la ligne a été ajoutée).
"""
from datetime import datetime
import os
import sqlite3
from pathlib import Path

from jobradar.parser import Job

DEFAULT_DB = Path(os.getenv("JOBRADAR_DB", Path(__file__).resolve().parents[2] / "data" / "jobs.db"))


def init_db(path: Path | str = DEFAULT_DB) -> sqlite3.Connection:
    """Ouvre la base, crée la table si besoin, renvoie la connexion."""
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)  # FastAPI utilise plusieurs threads
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    title TEXT,
                    company TEXT,
                    location TEXT,
                    work_mode TEXT,
                    url TEXT,
                    source TEXT,
                    first_seen TEXT,
                    status TEXT DEFAULT 'new'
                )
                """
    )
    _migrate(conn)
    return conn


def save_jobs(conn: sqlite3.Connection, jobs: list[Job]) -> int:
    """Insère les offres nouvelles. Renvoie le nombre d'offres réellement ajoutées."""
    added = 0
    now = datetime.now().isoformat()
    for job in jobs:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO jobs (job_id, title, company, location, work_mode, url, source, first_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.job_id,
                job.title,
                job.company,
                job.location,
                job.work_mode,
                job.url,
                job.source,
                now
            ),
        )
        added += cur.rowcount
    conn.commit()
    return added


def list_jobs(conn: sqlite3.Connection) -> list[dict]:
    """Renvoie toutes les offres, les plus récentes d'abord, sous forme de dicts."""
    cur = conn.execute(
        """
        SELECT job_id, title, company, location, work_mode, url, source, first_seen, status
        FROM jobs
        ORDER BY first_seen DESC
        """
    )
    
    return [dict(row) for row in cur.fetchall()]
    


def _migrate(conn: sqlite3.Connection) -> None:
    """Ajoute les colonnes de l'étape 3 si la base a été créée avant (migration simple)."""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}
    for col, typ in [("score", "REAL"), ("reasons", "TEXT"), ("status_updated_at", "TEXT")]:
        if col not in existing:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {typ}")
    conn.commit()


def unscored_jobs(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM jobs WHERE score IS NULL").fetchall()
    return [dict(r) for r in rows]


def set_score(conn: sqlite3.Connection, job_id: str, score: float, reasons: list[str]) -> None:
    conn.execute(
        "UPDATE jobs SET score = ?, reasons = ? WHERE job_id = ?",
        (score, ", ".join(reasons), job_id),
    )


def top_jobs(conn: sqlite3.Connection, limit: int = 10) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM jobs WHERE score IS NOT NULL ORDER BY score DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]
