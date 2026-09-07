from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Score:
    total: int
    breakdown: dict[str, int]
    maximums: dict[str, int]
    why: list[str]
    concerns: list[str]


def score_job(job: dict, profile: dict) -> Score:
    """Produce a deterministic, component-level score with no hidden model judgment."""
    haystack = f"{job.get('title', '')} {job.get('description', '')}".lower()
    title_hits = [term for term in profile["target_titles"] if term.lower() in haystack]
    skill_hits = [term for term in profile["target_skills"] if term.lower() in haystack]
    location = f"{job.get('location', '')} {job.get('workplace', '')}".lower()
    location_hits = [term for term in profile["preferred_locations"] if term.lower() in location]
    workplace = (job.get("workplace") or "").strip().lower()
    preferred_workplaces = [item.lower() for item in profile.get("preferred_workplaces", [])]
    workplace_match = next((item for item in preferred_workplaces if item == workplace), None)

    requested = job.get("experience_min")
    target_years = profile.get("target_experience_years", 0)
    experience_points = (
        20
        if requested is None or requested <= target_years
        else max(0, 20 - (requested - target_years) * 6)
    )

    minimum_salary = profile.get("minimum_salary")
    target_currency = profile.get("minimum_salary_currency")
    listed_salary = job.get("compensation_max") or job.get("compensation_min")
    comparable_currency = not target_currency or job.get("compensation_currency") == target_currency
    if not minimum_salary or listed_salary is None or not comparable_currency:
        compensation_points = 5
    elif listed_salary >= minimum_salary:
        compensation_points = 10
    else:
        compensation_points = 0

    maximums = {
        "role": 30,
        "skills": 25,
        "experience": 20,
        "location": 10,
        "flexibility": 5,
        "compensation": 10,
    }
    breakdown = {
        "role": min(30, 16 + 7 * len(title_hits)) if title_hits else 8,
        "skills": min(25, 6 * len(skill_hits)),
        "experience": experience_points,
        "location": min(10, 6 * len(location_hits)),
        "flexibility": 5 if workplace_match else (2 if not workplace else 0),
        "compensation": compensation_points,
    }
    why = []
    if title_hits:
        why.append(f"Role match: {', '.join(title_hits[:2])}")
    if skill_hits:
        why.append(f"Skill match: {', '.join(skill_hits[:3])}")
    if location_hits:
        why.append(f"Location match: {', '.join(location_hits[:2])}")
    if workplace_match:
        why.append(f"Work model match: {job['workplace']}")
    if minimum_salary and listed_salary and comparable_currency and listed_salary >= minimum_salary:
        why.append("Listed compensation meets the configured target")

    concerns = []
    if requested is not None and requested > target_years:
        concerns.append(f"Requests {requested}+ years; profile target is {target_years}")
    if not location_hits:
        concerns.append("Location preference is not explicit")
    if workplace and preferred_workplaces and not workplace_match:
        concerns.append(f"Work model is {job['workplace']}, outside the configured preferences")
    if minimum_salary and listed_salary is None:
        concerns.append("Compensation is not stated")
    elif minimum_salary and listed_salary and not comparable_currency:
        concerns.append("Listed compensation uses a different currency; no conversion was assumed")
    elif minimum_salary and listed_salary and listed_salary < minimum_salary:
        concerns.append("Listed compensation is below the configured target")
    return Score(sum(breakdown.values()), breakdown, maximums, why, concerns)
