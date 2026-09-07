from __future__ import annotations

import html
import re
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class FetchResult:
    source: dict
    jobs: tuple[dict, ...] = ()
    error: Exception | None = None


def plain_text(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", html.unescape(value or ""))
    return re.sub(r"\s+", " ", without_tags).strip()


def source_spec(config: dict) -> dict:
    kind = config["type"].lower()
    token = config["token"]
    return {
        "id": f"{kind}:{token}",
        "kind": kind,
        "company": config["company"],
        "label": config.get("label", config["company"]),
        "token": token,
        "allow_empty": config.get("allow_empty", False),
    }


def greenhouse(source: dict, client: httpx.Client) -> list[dict]:
    response = client.get(
        f"https://boards-api.greenhouse.io/v1/boards/{source['token']}/jobs",
        params={"content": "true"},
    )
    response.raise_for_status()
    return [
        {
            "source_job_id": str(job["id"]),
            "company": source["company"],
            "title": job["title"],
            "location": job.get("location", {}).get("name", "Not stated"),
            "description": plain_text(job.get("content", "")),
            "source_url": job.get("absolute_url"),
        }
        for job in response.json().get("jobs", [])
    ]


def lever(source: dict, client: httpx.Client) -> list[dict]:
    response = client.get(
        f"https://api.lever.co/v0/postings/{source['token']}", params={"mode": "json"}
    )
    response.raise_for_status()
    return [
        {
            "source_job_id": str(job["id"]),
            "company": source["company"],
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
        for job in response.json()
    ]


def ashby(source: dict, client: httpx.Client) -> list[dict]:
    response = client.get(
        f"https://api.ashbyhq.com/posting-api/job-board/{source['token']}",
        params={"includeCompensation": "true"},
    )
    response.raise_for_status()
    return [
        {
            "source_job_id": str(job.get("jobUrl") or job.get("applyUrl") or job["title"]),
            "company": source["company"],
            "title": job["title"],
            "location": job.get("location", "Not stated"),
            "description": plain_text(job.get("descriptionHtml", job.get("descriptionPlain", ""))),
            "source_url": job.get("jobUrl") or job.get("applyUrl"),
        }
        for job in response.json().get("jobs", [])
        if job.get("isListed", True)
    ]


def fetch_sources(sources: list[dict], timeout: float = 30) -> list[FetchResult]:
    """Fetch every configured board independently so one failure cannot poison the batch."""
    adapters = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby}
    results: list[FetchResult] = []
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        for config in sources:
            source = source_spec(config)
            try:
                adapter = adapters[source["kind"]]
                jobs = adapter(source, client)
                results.append(FetchResult(source=source, jobs=tuple(jobs)))
            except Exception as error:  # noqa: BLE001 - connector boundary isolates each source
                results.append(FetchResult(source=source, error=error))
    return results
