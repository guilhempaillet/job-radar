from __future__ import annotations

import html
import re

import httpx


def plain_text(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", html.unescape(value or ""))
    return re.sub(r"\s+", " ", without_tags).strip()


def greenhouse(company: str, token: str, client: httpx.Client) -> list[dict]:
    response = client.get(
        f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs",
        params={"content": "true"},
    )
    response.raise_for_status()
    return [
        {
            "id": f"greenhouse:{token}:{job['id']}",
            "company": company,
            "title": job["title"],
            "location": job.get("location", {}).get("name", "Not stated"),
            "description": plain_text(job.get("content", "")),
            "source_url": job.get("absolute_url"),
        }
        for job in response.json().get("jobs", [])
    ]


def lever(company: str, token: str, client: httpx.Client) -> list[dict]:
    response = client.get(f"https://api.lever.co/v0/postings/{token}", params={"mode": "json"})
    response.raise_for_status()
    jobs = response.json()
    return [
        {
            "id": f"lever:{token}:{job['id']}",
            "company": company,
            "title": job["text"],
            "location": job.get("categories", {}).get("location", "Not stated"),
            "description": plain_text(
                " ".join(
                    [job.get("descriptionPlain", ""), job.get("additionalPlain", "")]
                    + [item.get("content", "") for item in job.get("lists", [])]
                )
            ),
            "source_url": job.get("hostedUrl"),
        }
        for job in jobs
    ]


def ashby(company: str, token: str, client: httpx.Client) -> list[dict]:
    response = client.get(
        f"https://api.ashbyhq.com/posting-api/job-board/{token}",
        params={"includeCompensation": "true"},
    )
    response.raise_for_status()
    return [
        {
            "id": f"ashby:{token}:{job.get('jobUrl', job['title'])}",
            "company": company,
            "title": job["title"],
            "location": job.get("location", "Not stated"),
            "description": plain_text(job.get("descriptionHtml", job.get("descriptionPlain", ""))),
            "source_url": job.get("jobUrl") or job.get("applyUrl"),
        }
        for job in response.json().get("jobs", [])
        if job.get("isListed", True)
    ]


def fetch_sources(sources: list[dict], timeout: float = 30) -> list[dict]:
    adapters = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby}
    jobs: list[dict] = []
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        for source in sources:
            source_type = source["type"].lower()
            if source_type not in adapters:
                raise ValueError(f"Unsupported source type: {source_type}")
            jobs.extend(adapters[source_type](source["company"], source["token"], client))
    return jobs
