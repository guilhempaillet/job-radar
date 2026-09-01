import httpx

from job_radar.connectors import ashby, greenhouse, lever, plain_text


def client(payload):
    return httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    )


def test_plain_text_decodes_and_removes_markup():
    assert plain_text("<p>Build &amp; ship</p>") == "Build & ship"


def test_greenhouse_normalization():
    jobs = greenhouse(
        "Acme",
        "acme",
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
    assert jobs[0]["id"] == "greenhouse:acme:1"
    assert jobs[0]["description"] == "5+ years"


def test_lever_and_ashby_normalization():
    lever_jobs = lever(
        "Acme",
        "acme",
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
    ashby_jobs = ashby(
        "Acme",
        "acme",
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
