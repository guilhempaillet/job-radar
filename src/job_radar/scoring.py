from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Score:
    total: int
    breakdown: dict[str, int]
    why: list[str]
    concerns: list[str]


def score_job(job: dict, profile: dict) -> Score:
    haystack = f"{job.get('title', '')} {job.get('description', '')}".lower()
    title_hits = [x for x in profile["target_titles"] if x.lower() in haystack]
    skill_hits = [x for x in profile["target_skills"] if x.lower() in haystack]
    location = f"{job.get('location', '')} {job.get('workplace', '')}".lower()
    location_hits = [x for x in profile["preferred_locations"] if x.lower() in location]

    requested = job.get("experience_min")
    target = profile.get("target_experience_years", 0)
    exp_points = (
        20 if requested is None or requested <= target else max(0, 20 - (requested - target) * 6)
    )
    breakdown = {
        "role": min(30, 16 + 7 * len(title_hits)) if title_hits else 8,
        "skills": min(25, 6 * len(skill_hits)),
        "experience": exp_points,
        "location": min(15, 8 * len(location_hits)),
        "freshness": 10,
    }
    why = []
    if title_hits:
        why.append(f"Role match: {', '.join(title_hits[:2])}")
    if skill_hits:
        why.append(f"Skill match: {', '.join(skill_hits[:3])}")
    if location_hits:
        why.append(f"Location match: {', '.join(location_hits[:2])}")
    concerns = []
    if requested is not None and requested > target:
        concerns.append(f"Requests {requested}+ years; profile target is {target}")
    if not location_hits:
        concerns.append("Location preference is not explicit")
    return Score(min(100, sum(breakdown.values())), breakdown, why, concerns)
