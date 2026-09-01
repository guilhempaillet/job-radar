from job_radar.extraction import (
    benefits,
    binding_experience_minimum,
    experience_requirements,
    workplace_evidence,
)


def test_keeps_all_experience_evidence_and_uses_binding_requirement():
    text = "Requires 8+ years of product management and 3+ years with AI platforms."
    assert [int(x.value) for x in experience_requirements(text)] == [8, 3]
    assert binding_experience_minimum(text) == 8


def test_unknown_beats_guessing():
    assert binding_experience_minimum("Strong product judgment is important.") is None
    assert workplace_evidence("Work with a distributed customer base.") is None


def test_extracts_explicit_workplace_and_benefits():
    text = "This hybrid role includes equity, health coverage, a 401(k), and parental leave."
    assert workplace_evidence(text).value == "Hybrid"
    assert benefits(text) == ["Equity", "Health", "Retirement", "Parental leave"]
