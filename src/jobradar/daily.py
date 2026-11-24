"""Étape 5 : routine quotidienne. Lance : python -m jobradar.daily

1. Ingestion des nouvelles alertes Gmail
2. Scoring des nouvelles offres
3. Email récapitulatif (à moi-même) des nouvelles offres au-dessus du seuil
"""
import html
import os
from datetime import datetime, timedelta

from dotenv import load_dotenv

from jobradar import ingest, rank
from jobradar.db import init_db
from jobradar.gmail_client import get_service, send_email

load_dotenv()
MIN_SCORE = float(os.getenv("DIGEST_MIN_SCORE", 70))
DIGEST_TO = os.getenv("DIGEST_TO")  # ton adresse, dans .env


def new_good_jobs(conn, since: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM jobs WHERE first_seen >= ? AND score >= ? ORDER BY score DESC",
        (since, MIN_SCORE),
    ).fetchall()
    return [dict(r) for r in rows]


def build_html(jobs: list[dict]) -> str:
    lines = [f"<h2>Job Radar : {len(jobs)} nouvelle(s) offre(s)</h2><ul>"]
    for j in jobs:
        mode = f" ({html.escape(j['work_mode'])})" if j["work_mode"] else ""
        reasons = f" <i style='color:#888'>[{html.escape(j['reasons'])}]</i>" if j["reasons"] else ""
        lines.append(
            f"<li><b>{j['score']:.0f}</b> <a href='{j['url']}'>{html.escape(j['title'])}</a>"
            f" : {html.escape(j['company'])}, {html.escape(j['location'])}{mode}{reasons}</li>"
        )
    lines.append("</ul><p>Tableau de bord : http://127.0.0.1:8000</p>")
    return "\n".join(lines)


def main():
    since = (datetime.now() - timedelta(hours=1)).isoformat()  # offres ajoutées par ce lancement
    ingest.main()
    rank.main(limit=5)

    jobs = new_good_jobs(init_db(), since)
    if not jobs:
        print("Rien de nouveau au-dessus du seuil, pas d'email.")
        return
    if not DIGEST_TO:
        raise SystemExit("Ajoute DIGEST_TO=ton.adresse@gmail.com dans .env")
    subject = f"Job Radar {datetime.now():%d/%m} : {len(jobs)} offre(s) à regarder"
    send_email(get_service(), DIGEST_TO, subject, build_html(jobs))
    print(f"Email envoyé : {len(jobs)} offres")


if __name__ == "__main__":
    main()
