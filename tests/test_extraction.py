from job_radar.extraction import (
    benefit_evidence,
    binding_experience_minimum,
    compensation,
    experience_requirements,
    primary_workplace,
    workplace_evidence,
)


def test_keeps_all_experience_evidence_and_uses_binding_requirement():
    text = "Requirements: 8+ years of product management and 3+ years with AI platforms."
    evidence = experience_requirements(text)
    assert [int(item.value) for item in evidence] == [8, 3]
    assert all(item.quote.startswith("Requirements") for item in evidence)
    assert binding_experience_minimum(text) == 8


def test_preferred_experience_does_not_become_binding():
    text = "Requires 4+ years in product. 7+ years is preferred."
    assert binding_experience_minimum(text) == 4
    assert experience_requirements(text)[1].confidence == "medium"


def test_unknown_beats_guessing():
    assert binding_experience_minimum("Strong product judgment is important.") is None
    assert workplace_evidence("Work with a distributed customer base.") == []
    assert compensation("Competitive compensation is available.") is None


def test_extracts_multiple_workplace_options_and_benefit_receipts():
    text = "The role can be remote or hybrid. Benefits include equity and health coverage."
    workplaces = workplace_evidence(text)
    assert [item.value for item in workplaces] == ["Remote", "Hybrid"]
    assert primary_workplace(workplaces) == "Remote or hybrid"
    benefits = benefit_evidence(text)
    assert [item.value for item in benefits] == ["Equity", "Health"]
    assert all(item.quote in text for item in benefits)


def test_workplace_location_evidence_keeps_its_actual_source_field():
    evidence = workplace_evidence("Join the product team.", "Remote — Canada")
    assert evidence[0].source_field == "location"
    assert evidence[0].quote == "Remote — Canada"


def test_extracts_annual_compensation_without_converting_currency():
    cad = compensation("The base salary is CAD $155,000 to $195,000 per year.")
    assert (cad.minimum, cad.maximum, cad.currency, cad.period) == (
        155_000,
        195_000,
        "CAD",
        "year",
    )
    usd = compensation("Compensation is $190K–$245K USD per year.")
    assert (usd.minimum, usd.maximum, usd.currency) == (190_000, 245_000, "USD")
    assert compensation("Compensation is $190K–$245K per year.") is None
