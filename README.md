# Job Radar

**An evidence-first, local job search workspace.** Job Radar turns public job feeds into a ranked, reviewable queue while keeping source facts, automated analysis, and human decisions clearly separated.

The project is designed around a simple premise: job-search software should help you decide—not quietly invent facts or overwrite your memory.

> This repository is a privacy-safe product derivative. The bundled dataset is fictional, the default experience requires no accounts or API keys, and no personal job-search history is included.

![Job Radar desktop dashboard](docs/job-radar-desktop.jpg)

<details>
<summary>Mobile view</summary>

![Job Radar mobile dashboard](docs/job-radar-mobile.jpg)

</details>

## What it demonstrates

- **Evidence-backed extraction.** Experience, workplace, and benefits retain the exact source text that supports them. Missing data stays unknown.
- **Explainable ranking.** A deterministic score exposes role, skill, experience, location, and freshness components.
- **Human-owned workflow.** Shortlists, applications, dismissals, notes, and tags live in a separate table and survive every refresh.
- **Change intelligence.** Idempotent ingestion records additions and meaningful updates without turning them into notification noise.
- **Portfolio and company views.** Review individual roles or inspect opportunity density by company.
- **Responsive, local-first UI.** FastAPI, Jinja, and SQLite keep the stack inspectable and easy to run.

## Run the demo

Requires Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
job-radar init-demo
job-radar serve
```

Open [http://127.0.0.1:8876](http://127.0.0.1:8876). The demo loads eight fictional roles spanning remote, hybrid, and in-person work.

With Docker:

```bash
docker build -t job-radar .
docker run --rm -p 8876:8876 job-radar
```

## Product architecture

```text
public sources → normalized job facts → evidence + deterministic score
                                      ↘ change log
human review  → separate triage state → shortlist / applied / dismissed
```

The separation is intentional. A source refresh can update a title or mark a role inactive, but it cannot claim that a person applied. See [Architecture](docs/architecture.md) for the data boundaries and extension points.

## Configuration

Copy `config.example.yaml` to `config.yaml` and adapt the generic target profile. The bundled demo remains the no-network default. Opt-in Greenhouse, Lever, and Ashby adapters use public board tokens rather than credentials:

```bash
cp config.example.yaml config.yaml
# add public board tokens, then:
job-radar refresh-sources --config config.yaml
```

Environment variables:

| Variable | Default | Purpose |
|---|---:|---|
| `JOB_RADAR_DB` | `./job-radar.db` | SQLite database path |
| `JOB_RADAR_HOST` | `127.0.0.1` | Bind address |
| `JOB_RADAR_PORT` | `8876` | Web port |

## Quality and privacy

```bash
ruff check src tests
pytest --cov=job_radar
```

CI runs linting, tests, coverage, and a Gitleaks secret scan. The [privacy model](docs/privacy.md) documents what is intentionally excluded from the repository and the release checklist used before publication.

## Roadmap

- Connector health reporting and per-source failure isolation
- Salary evidence and currency normalization
- Saved filter views and keyboard triage
- Batch reconciliation proposals for application confirmations
- Optional local or hosted LLM adapter with cached, cited outputs
- Export/import and multi-profile support

Contributions and product critique are welcome. This is an early, opinionated release rather than a finished recruiting platform.
