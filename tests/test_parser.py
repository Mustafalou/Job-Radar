from pathlib import Path

import pytest

from jobradar.parser import parse_linkedin_alert

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "raw" / "1a1584659375af2f.html"


@pytest.mark.skipif(not SAMPLE.exists(), reason="email d'exemple absent")
def test_parse_sia_alert():
    jobs = parse_linkedin_alert(SAMPLE.read_text(encoding="utf-8"))

    assert len(jobs) == 4
    first = jobs[0]
    assert first.job_id == "4480992193"
    assert first.title == "Consultant in Data Science"
    assert first.company == "Sia"
    assert first.location == "Bruxelles"
    assert first.work_mode == "Hybride"
    assert first.url == "https://www.linkedin.com/jobs/view/4480992193/"

    titles = [j.title for j in jobs]
    assert "AI Engineer Consultant" in titles
    assert len({j.job_id for j in jobs}) == 4  # pas de doublons
