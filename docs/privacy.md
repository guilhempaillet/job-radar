# Privacy and release model

This repository was created as a clean product derivative, not as a mirror of a personal deployment.

## Intentionally excluded

- Personal resumes, profiles, applications, notes, contacts, and browsing history
- Production databases, snapshots, and job records
- Private hostnames, network details, and filesystem paths
- Credentials, browser sessions, email accounts, and proprietary connectors
- Git history from the private source system
- Private source configuration and deployment units

The bundled companies, jobs, descriptions, and links are fictional sample data.

## Optional external model boundary

Rule-based extraction is local and always runs first. The LLM fallback is disabled unless a user explicitly sets `llm_fallback.enabled: true`, configures an endpoint/model, and supplies a key through an environment variable. Enabling it sends job-description text to that configured provider. Model output is schema-validated and must cite exact source text before persistence.

No model credentials or calls are needed for the demo, tests, CI, or public ATS connectors.

## Before a public release

1. Run tests and linting.
2. Run Gitleaks across the full fresh history.
3. Search tracked files for usernames, home paths, private network ranges, resume names, and production hostnames.
4. Inspect screenshots for tabs, browser chrome, personal records, and machine identifiers.
5. Review the GitHub repository visibility and Actions logs.
6. Publish only after a second human review.
