"""Score les offres pas encore notées et affiche le top. Lance : python -m jobradar.rank"""
import sys

from jobradar.db import init_db, set_score, top_jobs, unscored_jobs
from jobradar.scoring import score_job


def main(limit: int = 10):
    conn = init_db()
    todo = unscored_jobs(conn)
    print(f"{len(todo)} offres à scorer...")
    for job in todo:
        score, reasons = score_job(job["title"])
        set_score(conn, job["job_id"], round(score, 1), reasons)
    conn.commit()

    print(f"\nTop {limit} :")
    for i, job in enumerate(top_jobs(conn, limit), 1):
        mode = f" ({job['work_mode']})" if job["work_mode"] else ""
        extra = f"  [{job['reasons']}]" if job["reasons"] else ""
        print(f"{i:>2}. {job['score']:>5.1f}  {job['title']} | {job['company']} | {job['location']}{mode}{extra}")
        print(f"           {job['url']}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 10)
