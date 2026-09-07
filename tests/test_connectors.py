import httpx

from job_radar.connectors import ashby, fetch_sources, greenhouse, lever, plain_text, source_spec


def client(payload, status=200):
    return httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(status, json=payload, request=request)
        )
    )


def test_plain_text_decodes_and_removes_markup():
    assert plain_text("<p>Build &amp; ship</p>") == "Build & ship"


def test_greenhouse_normalization():
    source = source_spec({"type": "greenhouse", "company": "Acme", "token": "acme"})
    jobs = greenhouse(
        source,
        client(
            {
                "jobs": [
                    {
                        "id": 1,
                        "title": "PM",
                        "location": {"name": "Remote"},
                        "content": "<p>5+ years</p>",
                        "absolute_url": "https://example.com/1",
                    }
                ]
            }
        ),
    )
    assert jobs[0]["source_job_id"] == "1"
    assert jobs[0]["description"] == "5+ years"


def test_lever_and_ashby_normalization():
    lever_source = source_spec({"type": "lever", "company": "Acme", "token": "acme"})
    lever_jobs = lever(
        lever_source,
        client(
            [
                {
                    "id": "abc",
                    "text": "PM",
                    "categories": {"location": "Toronto"},
                    "descriptionPlain": "Build",
                    "additionalPlain": "Ship",
                    "lists": [],
                    "hostedUrl": "https://example.com/lever",
                }
            ]
        ),
    )
    assert lever_jobs[0]["description"] == "Build Ship"
    ashby_source = source_spec({"type": "ashby", "company": "Acme", "token": "acme"})
    ashby_jobs = ashby(
        ashby_source,
        client(
            {
                "jobs": [
                    {
                        "title": "AI PM",
                        "location": "Remote",
                        "descriptionHtml": "<p>Lead</p>",
                        "jobUrl": "https://example.com/ashby",
                        "isListed": True,
                    }
                ]
            }
        ),
    )
    assert ashby_jobs[0]["description"] == "Lead"


def test_fetch_isolates_a_failed_source(monkeypatch):
    def fake_greenhouse(source, client):
        if source["token"] == "broken":
            raise httpx.ConnectError("offline")
        return [{"source_job_id": "1"}]

    monkeypatch.setattr("job_radar.connectors.greenhouse", fake_greenhouse)
    results = fetch_sources(
        [
            {"type": "greenhouse", "company": "Good", "token": "good"},
            {"type": "greenhouse", "company": "Broken", "token": "broken"},
        ]
    )
    assert len(results[0].jobs) == 1
    assert isinstance(results[1].error, httpx.ConnectError)
