"""Pipeline : Gmail -> parseur -> SQLite. Lance : python -m jobradar.ingest"""
from jobradar.db import init_db, save_jobs
from jobradar.gmail_client import get_html_body, get_service, list_alert_messages
from jobradar.parser import parse_linkedin_alert


def main():
    service = get_service()
    conn = init_db()
    ids = list_alert_messages(service)
    total_found, total_new = 0, 0

    for msg_id in ids:
        sender, subject, html = get_html_body(service, msg_id)
        if "linkedin" not in sender.lower():
            continue  # Indeed : parseur à écrire plus tard
        jobs = parse_linkedin_alert(html)
        total_found += len(jobs)
        total_new += save_jobs(conn, jobs)

    print(f"{len(ids)} emails lus, {total_found} offres trouvées, {total_new} nouvelles en base")


if __name__ == "__main__":
    main()
