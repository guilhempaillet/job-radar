# Architecture

Job Radar has four explicit layers:

1. **Source records** are normalized from a connector without modifying their meaning.
2. **Extracted facts** keep evidence and use `unknown` when the source is silent.
3. **Analysis** is derived and reproducible. The score breakdown is stored next to the total.
4. **Human state** records decisions, notes, and tags in a separate table.

## Why the separation matters

A source can change independently of the person reviewing it. Ingestion therefore owns `jobs`, while the user owns `human_state`. The refresh path never writes application status. This makes a failed extraction recoverable and a personal decision durable.

## Current schema

- `jobs`: current normalized facts, evidence, analysis, first/last seen, active state
- `human_state`: status, notes, tags, and last human update
- `changes`: append-only observations for added or changed source records
- `runs`: refresh-level operational history

## Extension points

Connectors should produce the small normalized job dictionary consumed by `refresh()`. Extraction and scoring are pure functions, making them straightforward to test against a gold fixture set. A future LLM adapter belongs after normalization and must return cited evidence; it should never write human state.

