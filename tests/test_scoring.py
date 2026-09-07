from job_radar.scoring import score_job

PROFILE = {
    "target_titles": ["product manager"],
    "target_skills": ["ai"],
    "preferred_locations": ["remote"],
    "preferred_workplaces": ["Remote", "Remote or hybrid"],
    "target_experience_years": 6,
    "minimum_salary": 180_000,
    "minimum_salary_currency": "USD",
}


def job(**overrides):
    base = {
        "title": "Product Manager, AI",
        "description": "Build AI products",
        "location": "Remote",
        "workplace": "Remote",
        "experience_min": 5,
        "compensation_min": 180_000,
        "compensation_max": 220_000,
        "compensation_currency": "USD",
    }
    return base | overrides


def test_score_breakdown_is_bounded_and_explainable():
    result = score_job(job(), PROFILE)
    assert result.total == sum(result.breakdown.values())
    assert all(result.breakdown[key] <= result.maximums[key] for key in result.breakdown)
    assert "Listed compensation meets" in " ".join(result.why)
    assert result.breakdown["flexibility"] == 5
    assert "Work model match" in " ".join(result.why)


def test_currency_mismatch_is_not_compared_as_equal():
    result = score_job(job(compensation_currency="CAD"), PROFILE)
    assert result.breakdown["compensation"] == 5
    assert "different currency" in " ".join(result.concerns)


def test_nonpreferred_work_model_is_visible_in_score_and_concerns():
    result = score_job(job(workplace="In person", location="San Francisco"), PROFILE)
    assert result.breakdown["flexibility"] == 0
    assert "outside the configured preferences" in " ".join(result.concerns)
