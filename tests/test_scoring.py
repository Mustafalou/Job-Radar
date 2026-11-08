from jobradar.scoring import rule_adjustment


def test_excluded():
    adj, reasons = rule_adjustment("Senior Firmware Engineer, Autonomous Systems")
    assert adj is None
    assert any("firmware" in r for r in reasons)


def test_senior_penalty():
    adj, _ = rule_adjustment("Senior Data Scientist (NLP, Python)")
    assert adj == -30


def test_junior_bonus():
    adj, _ = rule_adjustment("Junior AI Engineer")
    assert adj == 10


def test_neutral():
    adj, reasons = rule_adjustment("Consultant in Data Science")
    assert adj == 0
    assert reasons == []


def test_dutch_penalty():
    adj, reasons = rule_adjustment("Data Scientist - Dutch")
    assert adj == -20
    assert "langue: NL -20" in reasons


def test_word_boundary():
    adj, _ = rule_adjustment("Leadership Development Data Scientist")
    assert adj == 0  # "lead" ne doit pas matcher "leadership"


def test_electromechanical_excluded():
    adj, _ = rule_adjustment("Junior Electromechanical Engineering Consultant")
    assert adj is None
