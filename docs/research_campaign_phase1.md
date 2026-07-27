# PITNN Research Campaign Suite

The campaign runner is available at `scripts/run_research_campaign.py` and
uses a 240-point deterministic grid. It writes one JSONL record per point and
compact final-state arrays, avoiding a full trajectory tensor in RAM.

```powershell
.venv\Scripts\python.exe scripts\run_research_campaign.py `
  --fast-backend --fast-tda --fast-ep --mcwf-trajectories 32
.venv\Scripts\python.exe scripts\analyze_research_campaign.py
```

For validation, use `--steps 8 --max-nodes 4`. The production default is
100,000 spin steps per cached spin-control tuple. Cached tuples avoid repeating
identical spin dynamics for the independent pumping-rate axis; every grid node
still receives a separate record.

Outputs include `campaign_records.jsonl`, `campaign_arrays.npz`,
`full_campaign_matrix.npz`, `research_insights_summary.json`, and three
headless PNG plots. The reported critical pumping rate is explicitly labelled
as a grid heuristic, not a claim of complete decoherence suppression.
