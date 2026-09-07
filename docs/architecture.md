# Architecture and design decisions

Job Radar is intentionally a small, inspectable system: a command-line refresh path, SQLite, and a server-rendered FastAPI interface. The product boundary matters more than the number of services.

## Data flow

```text
configured public boards
        │
        ▼
connector normalization ── failure recorded per source
        │
        ▼
source records (`job_sources`)
        │
        ├── conservative identity match ──→ canonical roles (`jobs`)
        │                                      │
        │                                      ├── rule extraction + cited facts
        │                                      ├── optional cited LLM fallback
        │                                      └── deterministic score breakdown
        │
        └── refresh history (`runs`) + material role changes (`changes`)

human review ─────────────────────────────→ private state (`human_state`)
                                             status · tags · notes
```

## Source failure is not a closure

Connectors return one result per configured source. Fetching and persistence are isolated at that boundary:

- A source commits only after its complete payload is normalized and extracted.
- A source failure records a failed run and does not touch prior source mappings.
- An empty response after a previously non-empty response fails closed unless the source explicitly sets `allow_empty: true`.
- Missing records deactivate only mappings from the source that successfully refreshed.
- A canonical role closes only when none of its source mappings remain active.

This prevents one broken board from making unrelated jobs disappear.

## Conservative deduplication

The deduplication key normalizes company, title, and stated location. A new source record with the same key attaches to the existing canonical role. This is deliberately conservative: a different location remains a separate role rather than risking a false merge.

Canonical content comes from a stable primary source chosen deterministically. This avoids alternating URLs or descriptions when the same role arrives through two feeds. All observed sources remain visible on the role detail page.

## Facts before analysis

The extractor stores the result and its provenance separately:

- exact supporting sentence or substring;
- source field;
- extraction method (`rule` or `llm_fallback`);
- confidence.

Rules run first for experience, workplace, compensation, and benefits. Unknown is a valid result. Preferred experience is kept as evidence but does not become the binding minimum. Currency is stored, not converted silently.

If explicitly configured, the LLM fallback receives only the fields still missing. Its response must match a strict schema, and every field is rejected unless its quote is an exact substring of the source posting. This improves recall without turning model output into unreviewable fact.

## Explainable ranking

The default score is a configurable heuristic, not a model prediction. Every total is the sum of bounded components:

- role match: 30
- skill match: 25
- experience fit: 20
- location fit: 10
- work-model flexibility: 5
- compensation fit: 10

Each stored component includes both earned points and its maximum. Flexibility compares the posting's explicit work model with the configured workplace preferences. Compensation is compared with the configured floor only when currencies match; otherwise it remains neutral and produces a visible concern.

## Human state is a separate owner

Ingestion owns source facts. The user owns application status, tags, and notes. The refresh path never writes `human_state`, so a job-board edit cannot claim that a person applied or erase their context.

## Why server-rendered HTML

The current interaction model is filter, inspect, and submit a small form. FastAPI, Jinja, and plain CSS keep setup simple, work without a JavaScript build chain, and remain easy to audit. A richer client framework would add deployment and state complexity without improving the core workflow yet.
