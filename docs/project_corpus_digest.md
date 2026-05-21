# Project Corpus Digest (P37.1)
## Purpose
Local corpus scraper and claim-governed digestor for internal artifacts.
## Source taxonomy
manuscripts, simulator assets, OS/runtime, book systems, speculative ontology, governance.
## Architecture
`inventory -> digestor -> validator -> obsidian_sync -> command_center_payloads -> rag_pack`.
## Outputs
JSON registries, markdown reports, Obsidian mirrors, command-center payloads, RAG pack manifest.
## Validator + guardrails
Checks required files, required keys, forbidden phrases, and command-center false flags.
## Obsidian integration
Writes notes under `obsidian/10_Project_Corpus`.
## Command-center integration
Writes mock payloads under `outputs/command_center/mock_payloads`.
## RAG pack behavior
Safe-only by default; quarantined ontology excluded.
## What this does NOT claim
No proofs, no clinical efficacy claims, no real-data auto-execution, no API key exposure.
## How to run
Use Makefile targets `project-corpus-*` and `project-corpus-cycle`.
