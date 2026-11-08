from jobradar.db import init_db, list_jobs, save_jobs
from jobradar.parser import Job


def make_job(job_id, title="Data Scientist"):
    return Job(job_id, title, "Sia", "Bruxelles", "Hybride", f"https://www.linkedin.com/jobs/view/{job_id}/")


def test_save_and_list():
    conn = init_db(":memory:")  # base temporaire en mémoire, rien sur le disque
    assert save_jobs(conn, [make_job("1"), make_job("2")]) == 2

    jobs = list_jobs(conn)
    assert len(jobs) == 2
    assert jobs[0]["company"] == "Sia"
    assert jobs[0]["status"] == "new"


def test_no_duplicates():
    conn = init_db(":memory:")
    save_jobs(conn, [make_job("1")])
    assert save_jobs(conn, [make_job("1"), make_job("3")]) == 1  # seul le 3 est nouveau
    assert len(list_jobs(conn)) == 2


def test_scores():
    from jobradar.db import set_score, top_jobs, unscored_jobs
    conn = init_db(":memory:")
    save_jobs(conn, [make_job("1"), make_job("2", "Senior Data Scientist")])
    assert len(unscored_jobs(conn)) == 2
    set_score(conn, "1", 85.0, [])
    set_score(conn, "2", 50.0, ["senior: -30"])
    assert len(unscored_jobs(conn)) == 0
    assert top_jobs(conn, 1)[0]["job_id"] == "1"
