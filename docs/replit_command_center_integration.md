# Replit Command Center Integration
## Purpose
Expose stable backend contract for Replit frontend.
## Architecture
Replit frontend calls ScienceR-Dsim backend API only.
## Replit frontend role
Render status panels and chat UI.
## ScienceR-Dsim backend role
Serve command-center endpoints and guardrails.
## API base URL
Configured via `VITE_API_BASE_URL`.
## Endpoint map
/health /status /artifacts/manifest /rag/status /rag/query /rag/sync-plan /local-ops/status /tol/status /guardrails/status /actions/queue
## Mock payloads
Use outputs/command_center/mock_payloads/*.json for offline development.
## RAG chat panel
Default mock mode, show limitations and guardrails.
## Artifact explorer
Display source artifacts and citations.
## Local ops status panel
Display local ops health/state.
## ToL panel
Display ToL validation and synthesis state.
## Guardrails badges
no_ontology_promotion, q_qabs_fdress_candidate_telemetry_only, tol_quarantine_respected.
## Claim-scope badges
engineering_runtime_or_research_hypothesis.
## Source/citation display
Always show source_artifacts and citations arrays.
## Security
never put OPENAI_API_KEY in Replit frontend; frontend calls backend only; backend stores API key server-side; mock mode works without key; live mode requires explicit backend config.
## API key handling
Backend-only secret handling.
## What the frontend must never do
Never call OpenAI directly; never store secrets client-side; never infer ontology claims.

## P34 mental-health bridge status payload
The command-center mock payload set now includes `mental_health_bridge_status.json`, a research/wellness-safe status payload for the P34 mental-flexibility systems-medicine bridge. Guardrails keep diagnosis, clinical efficacy, and clinician-replacement claims blocked.
