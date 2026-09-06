# Review: Scrapling

- admission_status: rejected
- integration_mode: reject
- review_date: 2026-09-05

## Role
Adaptive HTML scraper. Default-denied.

## Evidence
https://scrapling.readthedocs.io/en/latest/ (BSD-3-Clause).

## Constraints
No fetchers in tests or CI. Any future use requires a human-approved URL from
`source_registry.json` allowlisted_public_documentation and a new work order.
Stealth/browser extras are a security risk.
